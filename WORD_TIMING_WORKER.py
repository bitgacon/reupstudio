"""Owned subprocess: bounded word-timestamp ASR, no project writes."""
import json,sys
from pathlib import Path
from reup import storage
from reup.word_timing import normalize_words

def main():
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));folder=Path(request['folder'])
    from faster_whisper import WhisperModel
    storage.atomic_json(folder/'word-progress.json',{'percent':10,'message':'Đang nạp Whisper CPU INT8…'})
    model=WhisperModel(request['model'],device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,download_root=request['cache'],local_files_only=not request['allow_download'])
    segments_only=request.get('segments_only') is True
    segments,info=model.transcribe(request['audio'],language=request['language'],vad_filter=True,word_timestamps=not segments_only,beam_size=3,condition_on_previous_text=False)
    rows=[]
    for segment in segments:
        rows.append(segment)
        storage.atomic_json(folder/'word-progress.json',{'percent':15+80*min(1,segment.end/max(info.duration,.1)),'message':f'Nhận dạng từ {segment.end:.1f}/{info.duration:.1f}s…'})
    if segments_only:
        cues=[]
        for segment in rows:
            start=max(0,round(segment.start*1000));end=min(request['duration_ms'],round(segment.end*1000));text=segment.text.strip()
            if text and end>start:cues.append({'id':len(cues)+1,'start_ms':start,'end_ms':end,'source_text':text,'text':text,'voice':'','status':'pending'})
        storage.atomic_json(folder/'word-result.json',{'cues':cues,'language':info.language})
    else:
        storage.atomic_json(folder/'word-result.json',{'words':normalize_words(rows,request['duration_ms']),'language':info.language,'message':'Mốc từ Whisper ước lượng từ audio, cần duyệt; không phải forced alignment lời dịch.'})

if __name__=='__main__':main()
