"""Read-only audio ASR proposals; isolated, cancellable CPU worker."""
import os,subprocess,sys,time
from . import storage,media,timeline,studio_tools

MODELS={'tiny','base','small','medium','large-v3','large-v3-turbo'}

def align_reference(reference,words):
    """Reuse only matching ASR word onsets; never invent translated-word timing."""
    import re,unicodedata
    from difflib import SequenceMatcher
    tokens=reference.split()
    if not 1<=len(tokens)<=400 or not 1<=len(words)<=2000:raise ValueError('Cần 1–400 từ tham chiếu và 1–2000 từ audio.')
    normal=lambda t:re.sub(r'[^\w]','',unicodedata.normalize('NFC',t).casefold())
    expected=[normal(w) for w in tokens];observed=[normal(w['word']) for w in words]
    if any(not w for w in expected):raise ValueError('Không dùng dấu câu/thẻ điều khiển đứng riêng trong lời tham chiếu.')
    matched={}
    for block in SequenceMatcher(None,expected,observed,autojunk=False).get_matching_blocks():
        for offset in range(block.size):matched[block.a+offset]=block.b+offset
    missing=[{'index':i+1,'word':word} for i,word in enumerate(tokens) if i not in matched]
    aligned=[{**words[matched[i]],'word':tokens[i]} for i in range(len(tokens)) if i in matched]
    return {'words':aligned,'coverage':len(matched)/len(tokens),'unmatched':missing,
            'can_apply':not missing,'message':'Dùng mốc từ khớp trong audio đang chọn; không dịch audio gốc và không phải forced alignment.'}

def proposal(payload,folder,event,progress):
    project,doc,track,c,source,item=studio_tools.selected(payload)
    if not item['has_audio'] or c['speed_curve'] or c['duration_ms']>300_000:
        raise ValueError('Chọn clip có audio tối đa 5 phút, tốc độ cố định; chia clip trước.')
    if event.is_set():raise InterruptedError('Đã dừng nhận dạng từ.')
    language=payload.get('language') or None
    if language not in {None,'vi','en','zh','ja','ko','fr','de','es','ru','th'}:raise ValueError('Ngôn ngữ nhận dạng không hỗ trợ.')
    model=storage.settings()['whisper_model']
    if model not in MODELS:raise ValueError('Model Whisper không hợp lệ.')
    folder.mkdir(parents=True,exist_ok=True);wav=folder/'words.wav'
    progress(3,'Đang trích audio đúng đoạn / tốc độ timeline…')
    timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(c['in_ms']/1000),'-t',str(c['duration_ms']*c['speed']/1000),'-i',str(source),'-vn','-af',timeline.tempo_filters(c['speed']),'-t',str(c['duration_ms']/1000),'-ac','1','-ar','16000',str(wav)],event)
    from .libraries import installed_path
    cache=installed_path('whisper',storage.DATA/'models'/'whisper')
    bundled=storage.ROOT/'whisper-models'/model
    if bundled.is_dir():model=str(bundled)
    else:
        # Reuse a complete locally installed snapshot read-only; do not copy models
        # into a QA/project folder or access any voice library.
        for root in [cache,storage.ROOT/'data'/'models'/'whisper']:
            hub=root/('models--Systran--faster-whisper-'+model)
            ref=hub/'refs'/'main'
            if ref.is_file():
                candidate=hub/'snapshots'/ref.read_text().strip()
                if candidate.is_dir() and all((candidate/f).is_file() for f in ['model.bin','config.json','tokenizer.json']):
                    model=str(candidate);break
    request={'audio':str(wav),'folder':str(folder),'model':model,'cache':str(cache),'language':language,'allow_download':payload.get('allow_download') is True,'duration_ms':c['duration_ms']}
    storage.atomic_json(folder/'word-request.json',request)
    env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1'}
    with (folder/'word-worker.log').open('w',encoding='utf-8') as log:
        from .libraries import whisper_python
        proc=subprocess.Popen([whisper_python(),str(storage.ROOT/'WORD_TIMING_WORKER.py'),str(folder/'word-request.json')],stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));started=time.monotonic();last=None;reported=0
        try:
            while proc.poll() is None:
                if event.wait(.5):raise InterruptedError('Đã dừng nhận dạng từ; timeline giữ nguyên.')
                if time.monotonic()-started>1800:raise RuntimeError('Nhận dạng quá 30 phút; dùng clip/model nhỏ hơn.')
                status=storage.read_json(folder/'word-progress.json',{})
                if status!=last or time.monotonic()-reported>10:
                    progress(min(95,status.get('percent',8)),status.get('message','Đang nạp Whisper CPU; lần đầu có thể lâu…'));last=status;reported=time.monotonic()
            if proc.returncode:raise RuntimeError('Nhận dạng từ thất bại: '+(folder/'word-worker.log').read_text(encoding='utf-8',errors='replace')[-1800:])
        finally:media.stop_owned_process(proc)
    if event.is_set():raise InterruptedError('Đã dừng nhận dạng từ.')
    result=storage.read_json(folder/'word-result.json',{})
    result.update(clip_id=c['id'],revision=doc['revision'],start_ms=c['start_ms'],duration_ms=c['duration_ms'])
    return result

def normalize_words(segments,duration_ms):
    """Whisper may emit CJK tokens/leading spaces or tiny overlaps; normalize safely."""
    rows=[];previous=0
    for segment in segments:
        for word in segment.words or []:
            if word.start is None or word.end is None:continue
            tokens=word.word.split()
            a=max(previous,round(word.start*1000));b=min(duration_ms,round(word.end*1000))
            if not tokens or b-a<len(tokens):continue
            for i,token in enumerate(tokens):
                rows.append({'word':token,'start':a+(b-a)*i//len(tokens),'end':a+(b-a)*(i+1)//len(tokens)})
            previous=b
    if not rows:raise ValueError('Không tìm thấy từ có mốc thời gian; thử đoạn có lời rõ hơn.')
    if len(rows)>2000:raise ValueError('Quá 2000 từ trong đề xuất; chia clip trước.')
    return rows
