"""Deterministic multilayer director; no LLM/network or existing-clip edits."""
import copy
from uuid import uuid4
from . import storage,timeline

def build(doc,items,options):
    result=copy.deepcopy(doc);style=options.get('style','story')
    if style not in {'story','news','podcast'}:raise ValueError('Phong cách phối không hợp lệ.')
    start=options.get('start_ms',0);duration=options.get('duration_ms',5000)
    if type(start) is not int or type(duration) is not int or start<0 or not 100<=duration<=60_000 or start+duration>3_600_000:raise ValueError('Phối lớp tối đa 60s trong timeline.')
    added=[]
    def track(kind,name,clip):
        added.append(timeline.Track(id=uuid4().hex,name=name,kind=kind,clips=[timeline.Clip(id=uuid4().hex,start_ms=start,duration_ms=duration,**clip)]).model_dump())
    for role in ('background','overlay','music'):
        key=options.get(role,'')
        if not key:continue
        if key not in result['assets'] or key not in items:raise ValueError('Media không thuộc dự án: '+role)
        item=items[key]
        if role=='music' and not item['has_audio'] or role!='music' and item['kind'] not in {'video','image'}:raise ValueError('Loại media không đúng vai trò: '+role)
        length=duration if item['kind']=='image' else min(duration,int(item['duration_ms']))
        if length<100:raise ValueError('Nguồn dưới 100ms.')
        clip={'asset':key,'label':'Phối · '+role,'volume':.15 if role=='music' else 0,
              'fit':'cover' if role=='background' else 'contain','fade_in_ms':min(300,length//3),'fade_out_ms':min(300,length//3)}
        if role=='overlay':clip.update(x=80,y=25,scale=.3 if style!='podcast' else .45,opacity=.85)
        track('audio' if role=='music' else 'video','Phối · '+role,clip);added[-1]['clips'][0]['duration_ms']=length
    title=options.get('title','')
    if not isinstance(title,str) or len(title)>300:raise ValueError('Tiêu đề tối đa 300 ký tự.')
    if title.strip():track('text','Phối · tiêu đề',{'text':title.strip(),'label':'Tiêu đề','font':'Be Vietnam Pro','font_size':36 if style=='news' else 42,'box':True,'y':18 if style!='news' else 85,'text_animation':'pop'})
    if not added:raise ValueError('Chọn ít nhất một lớp hoặc nhập tiêu đề.')
    # Background must stay below existing foreground layers (tracks draw bottom→top).
    backgrounds=[t for t in added if t['name']=='Phối · background']
    result['tracks']=backgrounds+result['tracks']+[t for t in added if t not in backgrounds]
    result=timeline.Timeline.model_validate(result).model_dump()
    return {'timeline':result,'added':[{'name':t['name'],'duration_ms':t['clips'][0]['duration_ms']} for t in added],
            'message':'Phối lớp bằng quy tắc bố cục local, không phải AI sinh nội dung. Nguồn/clip cũ giữ nguyên; duyệt và Hoàn tác.'}

def proposal(payload,event):
    if event.is_set():raise InterruptedError('Đã dừng phối lớp.')
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Timeline đã đổi; tạo đề xuất lại.')
    options=payload.get('options',{})
    if not isinstance(options,dict):raise ValueError('Tùy chọn phối lớp không hợp lệ.')
    items={key:timeline.describe(project,key) for key in {options.get(k,'') for k in ('background','overlay','music')} if key and key in doc['assets']}
    return build(doc,items,options)
