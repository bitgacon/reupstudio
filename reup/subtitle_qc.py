"""Read-only subtitle review. Estimates are not forced alignment or TTS timing."""
import re
from . import editor,media,reading,storage

def estimate_cue(cue,rules=None):
    """Reading-rule-aware heuristic only; not a measured TTS duration."""
    rules=reading.config(storage.reading_settings()) if rules is None else rules
    parts=reading.pieces(cue.get('text',''),rules)
    words=sum(len(re.sub(r'\[[^\]]*\]','',p.get('spoken','')).split()) for p in parts)
    pauses=sum(p.get('silence',0) for p in parts)/1000
    rate=max(.5,float(cue.get('rate') or 1));slot=(cue['end_ms']-cue['start_ms'])/1000
    base=words/4.5+pauses;seconds=base/rate
    factor=max(1,seconds/slot) if slot>0 else None
    return {'text':cue.get('text',''),'rate':rate,'start_ms':cue['start_ms'],'end_ms':cue['end_ms'],
            'seconds':round(seconds,3),'speed':round(rate*factor,3) if factor is not None else None,
            'min_seconds':round(base*.8/rate,3),'max_seconds':round(base*1.25/rate,3),'words':words,
            'warning':slot<=0 or (factor is not None and rate*factor>1.3)}

def review(project):
    cues=project.get('cues',[]);issues=[]
    for issue in media.validate_cues(cues):
        issues.append({**issue,'cue':cues[issue['cue']-1]['id']})
    rules=reading.config(storage.reading_settings());config=editor.config(project.get('edit'))
    for cue in cues:
        text=cue.get('text','');duration=(cue['end_ms']-cue['start_ms'])/1000
        def warn(message):issues.append({'cue':cue['id'],'level':'warning','message':message})
        if re.search(r'[\u3400-\u9fff]',text):warn('Lời đọc Việt còn ký tự Trung; kiểm tra dịch/tên riêng trước khi tạo giọng.')
        if config['target_language']!='vi' and (not cue.get('translation','').strip() or cue.get('translation_language')!=config['target_language']):warn('Thiếu bản dịch đúng ngôn ngữ phụ đề đích.')
        if text.strip() and duration>0:
            estimate=estimate_cue(cue,rules)
            if estimate['warning'] and not (cue.get('audio') and cue.get('status') in ('complete','review')):
                warn(f'Lời đọc có thể nhanh: ước tính {estimate["speed"]:.2f}×, {estimate["min_seconds"]:.1f}–{estimate["max_seconds"]:.1f}s / khung {duration:.1f}s. Rút gọn trước khi tạo audio; không phải đo audio thật.')
        if cue.get('audio') and cue.get('status') in ('complete','review'):
            speed=float(cue.get('generated_rate',cue.get('rate') or 1))*float(cue.get('speed_factor') or 1)
            if speed>1.3:warn(f'Audio thực tế {speed:.2f}× (tốc độ đặt × hệ số căn); nghe thử và rút gọn nếu nhanh.')
    return {'cues':len(cues),'issues':issues}
