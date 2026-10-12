"""Provider contracts: local inference is offline; cloud needs per-request consent."""
import os,re,subprocess,time
from pathlib import Path
from uuid import uuid4
import requests
from pydantic import BaseModel,ConfigDict,Field,model_validator
from . import storage,media

LANGUAGES={'vi':'Tiếng Việt','en':'English','en-us':'English · US','en-gb':'English · UK','zh':'中文','ja':'日本語','ko':'한국어','fr':'Français','de':'Deutsch','es':'Español','pt':'Português','it':'Italiano','ru':'Русский','hi':'हिन्दी'}
EMOTIONS={'neutral':'Bình thường','happy':'Vui','sad':'Buồn','angry':'Giận','surprised':'Ngạc nhiên','whisper':'Thì thầm','story':'Kể chuyện','expressive':'Biểu cảm mạnh'}
COMMON=['en','zh','ja','ko','fr','de','es','pt','it','ru','hi']
CATALOG=[
    {'id':'vieneu','name':'VieNeu · tiếng Việt','languages':['vi'],'emotions':['neutral'],'instruction':False,'cloud':False},
    {'id':'kokoro','name':'Kokoro · local nhẹ','languages':['en-us','en-gb','es','fr','hi','it','ja','pt','zh'],'emotions':['neutral'],'instruction':False,'cloud':False},
    {'id':'chatterbox','name':'Chatterbox · đa ngôn ngữ','languages':COMMON,'emotions':['neutral','expressive'],'instruction':False,'cloud':False},
    {'id':'elevenlabs','name':'ElevenLabs · API','languages':['vi',*COMMON],'emotions':[k for k in EMOTIONS if k!='expressive'],'instruction':False,'cloud':True},
    {'id':'qwen','name':'Qwen3-TTS · diễn xuất','languages':[k for k in COMMON if k!='hi'],'emotions':[k for k in EMOTIONS if k!='expressive'],'instruction':True,'cloud':False}]

class SpeechOptions(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    provider:str=Field(default='vieneu',pattern=r'^(vieneu|kokoro|chatterbox|elevenlabs|qwen)$')
    language:str=Field(default='vi',max_length=10)
    voice:str=Field(default='',max_length=64,pattern=r'^[\w .\-]*$')
    emotion:str=Field(default='neutral',max_length=20)
    intensity:float=Field(default=.5,ge=0,le=1)
    instruction:str=Field(default='',max_length=500)
    cloud_consent:bool=Field(default=False,strict=True)
    model:str=Field(default='',pattern=r'^(|eleven_v3|eleven_multilingual_v2)$')
    reference_asset:str=Field(default='',pattern=r'^(|[a-f0-9]{32})$')
    reference_consent:bool=Field(default=False,strict=True)
    @model_validator(mode='after')
    def capabilities(self):
        row=next(r for r in CATALOG if r['id']==self.provider)
        if self.language not in row['languages']:raise ValueError('Bộ TTS không hỗ trợ ngôn ngữ này.')
        if self.emotion not in row['emotions']:raise ValueError('Bộ TTS không hỗ trợ cảm xúc này; không giả lập bằng tốc độ/cao độ.')
        if self.instruction and not row['instruction']:raise ValueError('Mô tả diễn xuất chỉ dùng với Qwen3-TTS.')
        if self.provider!='elevenlabs' and self.model:raise ValueError('Model API chỉ áp dụng ElevenLabs.')
        if self.provider=='elevenlabs' and self.model=='eleven_multilingual_v2' and self.emotion!='neutral':raise ValueError('Chọn Eleven v3 để sử dụng thẻ cảm xúc.')
        if self.reference_asset and (self.provider!='chatterbox' or not self.reference_consent):raise ValueError('Mẫu giọng chỉ dùng Chatterbox và phải xác nhận quyền sử dụng.')
        return self

def options(value=None):return SpeechOptions.model_validate(value or {}).model_dump()
def podcast_options(value=None):
    if value is None:return {}
    if not isinstance(value,dict) or len(value)>100:raise ValueError('Tối đa 100 cấu hình giọng nhân vật.')
    result={}
    for name,opt in value.items():
        if not isinstance(name,str) or not name.strip() or len(name)>60:raise ValueError('Tên nhân vật phải có 1–60 ký tự.')
        result[name]=options(opt)
    return result

def preflight(opt):
    if opt['provider']=='vieneu':return
    if not opt['voice']:raise ValueError('Chưa chọn giọng '+opt['provider']+'.')
    if opt['provider']=='elevenlabs':
        if not opt['cloud_consent']:raise ValueError('Chưa cho phép gửi lời đọc đến ElevenLabs.')
        if not config()['elevenlabs_key']:raise ValueError('Chưa cấu hình API key ElevenLabs.')
        return
    from .libraries import registry
    entry=registry().get('tts-'+opt['provider'],{})
    if not entry.get('python') or not Path(entry['python']).is_file():raise ValueError('Chưa cài '+opt['provider']+'. Vào Cài đặt → Thư viện tùy chọn.')

def effective(cue,project):return options(cue.get('tts') or project.get('tts'))
def signature(cue,project):
    opt=effective(cue,project)
    return {'tts':opt,'tts_driver':1} if opt['provider']!='vieneu' or opt['voice'] else {}

def config(value=None):
    with storage.LOCK:
        current=storage.read_json(storage.DATA/'tts-provider-settings.json',{'elevenlabs_key':'','device':'cpu'})
        if value is not None:
            if set(value)-{'elevenlabs_key','clear_key','device'}:raise ValueError('Cấu hình bộ TTS không hợp lệ.')
            if 'device' in value:
                if value['device'] not in {'cpu','cuda'}:raise ValueError('Chọn CPU hoặc NVIDIA CUDA.')
                current['device']=value['device']
            if value.get('clear_key') is True:current['elevenlabs_key']=''
            if value.get('elevenlabs_key'):
                key=value['elevenlabs_key']
                if not isinstance(key,str) or len(key)>512 or re.search(r'\s',key):raise ValueError('API key không hợp lệ.')
                current['elevenlabs_key']=key
            storage.atomic_json(storage.DATA/'tts-provider-settings.json',current)
        return current

def public():
    from .libraries import registry
    runtimes=registry();result=[]
    for row in CATALOG:
        entry=runtimes.get('tts-'+row['id'],{});voices=[]
        if entry.get('path'):
            path=Path(entry['path']);voices=storage.read_json(path/'voices.json',[])
        if row['id']=='chatterbox':voices=[{'id':'default','name':'Giọng mẫu mặc định','language':lang} for lang in row['languages']]
        if row['id']=='qwen' and not voices:voices=[{'id':v,'name':v,'language':''} for v in ['vivian','serena','uncle_fu','dylan','eric','ryan','aiden','ono_anna','sohee']]
        if row['id']=='elevenlabs':voices=storage.read_json(storage.DATA/'elevenlabs-voices.json',[])
        installed=bool(entry.get('python')) and Path(entry['python']).is_file()
        if row['id']=='vieneu':
            from .engine import find_home
            try:find_home();installed=True
            except RuntimeError:installed=False
        result.append({**row,'installed':installed,'voices':voices})
    return {'catalog':result,'languages':LANGUAGES,'emotions':EMOTIONS,'has_elevenlabs_key':bool(config()['elevenlabs_key']),'device':config()['device']}

def refresh_elevenlabs(event):
    key=config()['elevenlabs_key']
    if not key:raise ValueError('Nhập API key ElevenLabs trong Cài đặt → TTS đa ngôn ngữ.')
    if event.is_set():raise InterruptedError('Đã dừng tải danh sách giọng.')
    with requests.Session() as session:
        session.trust_env=False
        response=session.get('https://api.elevenlabs.io/v1/voices',headers={'xi-api-key':key},timeout=(10,20),allow_redirects=False)
        if response.status_code!=200:raise ValueError(f'ElevenLabs HTTP {response.status_code}; kiểm tra key/quyền truy cập. Không tự đổi key.')
        try:rows=response.json()['voices']
        except (ValueError,KeyError):raise ValueError('ElevenLabs trả danh sách giọng không hợp lệ.') from None
    voices=[{'id':r['voice_id'],'name':str(r.get('name','Giọng'))[:100],'language':''} for r in rows[:1000] if re.fullmatch(r'[A-Za-z0-9_-]{1,64}',r.get('voice_id',''))]
    if event.is_set():raise InterruptedError('Đã dừng tải danh sách giọng.')
    storage.atomic_json(storage.DATA/'elevenlabs-voices.json',voices)
    return {'voices':voices,'message':'Đã tải danh sách giọng qua API chính thức; chưa tạo audio.'}

class Speaker:
    def __init__(self,opt,folder,event,progress):
        self.opt=options(opt);self.folder=folder;self.event=event;self.progress=progress;self.proc=None;self.log=None
    def close(self):
        if self.proc:media.stop_owned_process(self.proc)
        if self.log:self.log.close()
    def speak(self,text,voice,output):
        if self.event.is_set():raise InterruptedError('Đã dừng TTS.')
        opt=self.opt;voice=opt['voice'] or voice
        if opt['provider']=='elevenlabs':return self.cloud(text,voice,output)
        if not self.proc:self.start()
        key=uuid4().hex;done=self.folder/(key+'-done.json');raw=self.folder/(key+'.wav')
        command={'text':text,'voice':voice,'options':opt,'output':str(raw),'done':str(done)}
        self.proc.stdin.write(__import__('json').dumps(command,ensure_ascii=False)+'\n');self.proc.stdin.flush();started=time.monotonic()
        while not done.is_file():
            if self.event.wait(.2):raise InterruptedError('Đã dừng TTS; không thay dữ liệu nguồn.')
            if self.proc.poll() is not None:raise RuntimeError('Runtime TTS dừng: '+(self.folder/'worker.log').read_text(encoding='utf-8',errors='replace')[-1400:])
            if time.monotonic()-started>900:raise RuntimeError('Tạo một đoạn TTS quá 15 phút; dùng đoạn ngắn/model nhỏ hơn.')
        status=storage.read_json(done)
        if status.get('error'):raise ValueError(status['error'])
        if not raw.is_file() or raw.stat().st_size<44:raise ValueError('Bộ TTS chưa trả audio hợp lệ.')
        media.transcode(raw,output);raw.unlink(missing_ok=True)
    def start(self):
        from .libraries import registry
        entry=registry().get('tts-'+self.opt['provider'],{})
        if not entry.get('python') or not Path(entry['python']).is_file():raise ValueError('Chưa cài '+self.opt['provider']+'. Vào Cài đặt → Thư viện tùy chọn; không tự tải khi chạy.')
        self.folder.mkdir(parents=True,exist_ok=True);request={**entry,'provider':self.opt['provider'],'device':config()['device']}
        if self.opt['reference_asset']:
            ref,_=storage.asset(self.opt['reference_asset']);request['reference']=str(ref)
        path=self.folder/'runtime.json';storage.atomic_json(path,request)
        env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1','PYTHONNOUSERSITE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
        env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
        self.log=(self.folder/'worker.log').open('w',encoding='utf-8')
        self.proc=subprocess.Popen([entry['python'],str(storage.ROOT/'TTS_PROVIDER_WORKER.py'),'serve',str(path)],stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,text=True,encoding='utf-8',env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def cloud(self,text,voice,output):
        opt=self.opt;key=config()['elevenlabs_key']
        if not opt['cloud_consent']:raise ValueError('Chưa cho phép gửi văn bản đến ElevenLabs.')
        if not key:raise ValueError('Chưa cấu hình API key ElevenLabs.')
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}',voice):raise ValueError('Chọn Voice ID ElevenLabs hợp lệ.')
        tags={'happy':'[happy]','sad':'[sad]','angry':'[angry]','surprised':'[surprised]','whisper':'[whispers]','story':'[storytelling]'}
        spoken=(tags.get(opt['emotion'],'')+' '+text).strip();model=opt['model'] or 'eleven_v3'
        body={'text':spoken,'model_id':model}
        if model!='eleven_multilingual_v2':body['language_code']=opt['language']
        partial=output.with_suffix('.download.mp3');output.parent.mkdir(parents=True,exist_ok=True)
        try:
            with requests.Session() as session:
                session.trust_env=False
                with session.post('https://api.elevenlabs.io/v1/text-to-speech/'+voice,params={'output_format':'mp3_44100_128'},headers={'xi-api-key':key,'Accept':'audio/mpeg'},json=body,stream=True,timeout=(10,30),allow_redirects=False) as response:
                    if response.status_code!=200:raise ValueError(f'ElevenLabs HTTP {response.status_code}: kiểm tra key, model, giọng hoặc hạn mức. Không tự thử lại để tránh tính phí trùng.')
                    content_type=response.headers.get('Content-Type','').split(';')[0].lower()
                    if not content_type.startswith('audio/') and content_type!='application/octet-stream':raise ValueError('ElevenLabs chưa trả audio hợp lệ; không tự gửi lại yêu cầu.')
                    total=0;started=time.monotonic()
                    with partial.open('wb') as file:
                        for block in response.iter_content(8192):
                            if self.event.is_set():raise InterruptedError('Đã dừng ElevenLabs; dịch vụ có thể đã tính credit cho yêu cầu gửi trước đó.')
                            total+=len(block)
                            if total>20_000_000 or time.monotonic()-started>180:raise ValueError('Audio API vượt giới hạn dung lượng/thời gian.')
                            file.write(block)
            if not partial.stat().st_size:raise ValueError('ElevenLabs trả audio trống.')
            media.transcode(partial,output)
        finally:partial.unlink(missing_ok=True)
