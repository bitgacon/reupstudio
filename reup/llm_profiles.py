"""Named LLM configurations. Manual selection, never quota-driven key rotation."""
from uuid import uuid4
from urllib.parse import urlsplit
from . import storage,translation_api

PRESETS=[
    {'id':'gemini','name':'Gemini','url':translation_api.GEMINI_URL,'model':'gemini-3.8-flash'},
    {'id':'openai','name':'OpenAI','url':'https://api.openai.com/v1','model':''},
    {'id':'deepseek','name':'DeepSeek','url':'https://api.deepseek.com','model':''},
    {'id':'openrouter','name':'OpenRouter','url':'https://openrouter.ai/api/v1','model':''},
    {'id':'custom','name':'API tương thích / local','url':'','model':''}]

def read():return storage.read_json(storage.DATA/'llm-profiles.json',{'active':'','profiles':[]})

def public():
    data=read()
    return {'active':data['active'],'presets':PRESETS,'profiles':[{k:v for k,v in row.items() if k!='key'}|{'has_key':bool(row.get('key'))} for row in data['profiles']]}

def save(body):
    if not isinstance(body,dict) or set(body)-{'id','name','provider','url','model','key','use_current_key','batch_size','pause_seconds'}:raise ValueError('Cấu hình LLM không hợp lệ.')
    for key in ('id','name','provider','url','model','key'):
        if key in body and (not isinstance(body[key],str) or len(body[key])>4096):raise ValueError('Cấu hình LLM không hợp lệ.')
    with storage.LOCK:
        data=read();pid=body.get('id') or uuid4().hex;storage.identifier(pid)
        old=next((r for r in data['profiles'] if r['id']==pid),{})
        if not old and len(data['profiles'])>=50:raise ValueError('Tối đa 50 cấu hình LLM.')
        name=body.get('name','').strip()[:80]
        if not name:raise ValueError('Đặt tên cấu hình, ví dụ Gemini công việc.')
        url,model=translation_api.normalize(body.get('url',''),body.get('model',''))
        parsed=urlsplit(url)
        if (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1'})) or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('URL API phải HTTPS hoặc HTTP localhost, không chứa key/thông tin đăng nhập.')
        if not model:raise ValueError('Nhập mã model API được tài khoản của bạn hỗ trợ.')
        key=body.get('key',old.get('key',''))
        if body.get('use_current_key') is True and not old and not key:
            current=storage.settings()
            if url==current['translation_url']:key=current['translation_key']
        if parsed.hostname not in {'localhost','127.0.0.1'} and not key:raise ValueError('Nhập API key cho cấu hình mới.')
        if old and urlsplit(old['url']).hostname!=parsed.hostname and 'key' not in body:raise ValueError('Đổi nhà cung cấp cần nhập key mới, không tự dùng lại key cũ.')
        if body.get('provider','custom') not in {p['id'] for p in PRESETS}:raise ValueError('Nhà cung cấp không hợp lệ.')
        try:batch=int(body.get('batch_size',10));pause=float(body.get('pause_seconds',2))
        except (ValueError,TypeError,OverflowError):raise ValueError('Batch/khoảng nghỉ API không hợp lệ.')
        if not 1<=batch<=20 or not 0<=pause<=60:raise ValueError('Batch 1–20 cue; khoảng nghỉ 0–60 giây.')
        row={'id':pid,'name':name,'provider':body.get('provider','custom'),'url':url,'model':model,'key':key,'batch_size':batch,'pause_seconds':pause}
        data['profiles']=[r for r in data['profiles'] if r['id']!=pid]+[row]
        storage.atomic_json(storage.DATA/'llm-profiles.json',data)
    return public()

def activate(pid):
    storage.identifier(pid)
    with storage.LOCK:
        data=read();row=next((r for r in data['profiles'] if r['id']==pid),None)
        if not row:raise ValueError('Không tìm thấy cấu hình LLM.')
        storage.save_settings({'translation_url':row['url'],'translation_model':row['model'],'translation_key':row['key'],'translation_batch':str(row['batch_size']),'translation_pause':str(row['pause_seconds'])})
        data['active']=pid;storage.atomic_json(storage.DATA/'llm-profiles.json',data)
    return public()

def delete(pid):
    storage.identifier(pid)
    with storage.LOCK:
        data=read();data['profiles']=[r for r in data['profiles'] if r['id']!=pid]
        if data['active']==pid:data['active']=''
        storage.atomic_json(storage.DATA/'llm-profiles.json',data)
    return public()
