"""Owned persistent local worker. Serve mode cannot download models."""
import json,os,sys
from pathlib import Path
REVISIONS={'chatterbox':'5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18','qwen':'0c0e3051f131929182e2c023b9537f8b1c68adfe'}

def offline():
    # HF flags alone do not stop a third-party tokenizer from downloading via requests.
    import socket
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    def blocked(*args,**kwargs):raise OSError('Runtime TTS offline: thiếu tài nguyên thì cài lại thư viện, không tự tải khi đọc.')
    socket.create_connection=blocked;socket.socket.connect=blocked;socket.socket.connect_ex=blocked

def write(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)

def load(request):
    provider=request['provider'];home=Path(request['path']);model=home/'model'
    if provider=='kokoro':
        from kokoro_onnx import Kokoro
        return Kokoro(str(home/'kokoro-v1.0.onnx'),str(home/'voices-v1.0.bin'))
    import torch
    device=request.get('device','cpu')
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('Đã chọn CUDA nhưng runtime/GPU chưa hỗ trợ. Chọn CPU hoặc cài lại bộ CUDA phù hợp.')
    torch.set_num_threads(2)
    if provider=='chatterbox':
        # PyPI 0.1.7 uses V2; upstream main's optional V3 argument is not in this wheel.
        required=['ve.pt','s3gen.pt','t3_mtl23ls_v2.safetensors','grapheme_mtl_merged_expanded_v1.json','conds.pt','Cangjie5_TC.json']
        if any(not (model/name).is_file() for name in required):raise ValueError('Thiếu model Chatterbox V2; bấm cài lại thư viện.')
        from chatterbox.models.tokenizers import tokenizer as tokenizers
        def local_hub_file(repo_id,filename,**kwargs):
            if repo_id!='ResembleAI/chatterbox' or filename!='Cangjie5_TC.json':raise ValueError('Runtime chỉ cho phép bảng Cangjie local đã cài.')
            return str(model/filename)
        # Its tokenizer otherwise calls hf_hub_download even when from_local is used.
        tokenizers.hf_hub_download=local_hub_file
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_local(model,device)
    if provider=='qwen':
        from qwen_tts import Qwen3TTSModel
        dtype=torch.bfloat16 if device=='cuda' and torch.cuda.is_bf16_supported() else torch.float16 if device=='cuda' else torch.float32
        return Qwen3TTSModel.from_pretrained(str(model),device_map='cuda:0' if device=='cuda' else 'cpu',dtype=dtype,attn_implementation='sdpa',local_files_only=True)
    raise ValueError('Local TTS không hỗ trợ.')

def speak(engine,request,command):
    import numpy as np
    import soundfile as sf
    opt=command['options'];provider=request['provider'];voice=command['voice'];text=command['text']
    if provider=='kokoro':
        languages={'en-us':'en-us','en-gb':'en-gb','es':'es','fr':'fr-fr','hi':'hi','it':'it','ja':'ja','pt':'pt-br','zh':'cmn'}
        prefix={'en-us':'a','en-gb':'b','es':'e','fr':'f','hi':'h','it':'i','ja':'j','pt':'p','zh':'z'}[opt['language']]
        if not voice.startswith(prefix):raise ValueError('Giọng Kokoro không khớp ngôn ngữ đã chọn.')
        audio,sr=engine.create(text,voice=voice,speed=1,lang=languages[opt['language']])
    elif provider=='chatterbox':
        if voice!='default':raise ValueError('Chatterbox dùng giọng mẫu hoặc mẫu audio riêng; chọn default.')
        exaggeration=.5 if opt['emotion']=='neutral' else .5+opt['intensity']*.5
        audio=engine.generate(text,language_id=opt['language'],audio_prompt_path=request.get('reference'),exaggeration=exaggeration,cfg_weight=.3 if opt['emotion']=='expressive' else .5)
        audio=audio.detach().cpu().numpy().reshape(-1);sr=engine.sr
    else:
        languages={'en':'English','zh':'Chinese','ja':'Japanese','ko':'Korean','fr':'French','de':'German','es':'Spanish','pt':'Portuguese','it':'Italian','ru':'Russian'}
        instructions={'neutral':'','happy':'Speak happily.','sad':'Speak sadly.','angry':'Speak angrily.','surprised':'Speak with surprise.','whisper':'Speak in a quiet whisper.','story':'Tell a story warmly, with expressive pacing.'}
        direction=opt['instruction'] or instructions[opt['emotion']]
        if direction:direction+=(' Use a subtle delivery.' if opt['intensity']<.34 else ' Use a strongly expressive delivery.' if opt['intensity']>.66 else '')
        wavs,sr=engine.generate_custom_voice(text=text,language=languages[opt['language']],speaker=voice,instruct=direction,max_new_tokens=2048)
        audio=np.asarray(wavs[0]).reshape(-1)
    if not len(audio) or not np.isfinite(audio).all() or len(audio)>sr*180:raise ValueError('Audio TTS trống/không hợp lệ/quá 3 phút mỗi đoạn.')
    sf.write(command['output'],audio,sr,subtype='PCM_16')

def manifest(engine,request):
    if request['provider']=='kokoro':
        prefix={'a':'en-us','b':'en-gb','e':'es','f':'fr','h':'hi','i':'it','j':'ja','p':'pt','z':'zh'}
        return [{'id':name,'name':name,'language':prefix[name[0]]} for name in engine.voices.files if name[0] in prefix]
    if request['provider']=='qwen':return [{'id':name,'name':name,'language':''} for name in engine.get_supported_speakers()]
    return [{'id':'default','name':'Giọng mẫu mặc định','language':''}]

def main(mode,request):
    home=Path(request['path']);os.environ['HF_HOME']=str(home/'hf');os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'
    if mode not in {'install','check','serve'}:raise ValueError('Chế độ worker không hợp lệ.')
    if mode in {'check','serve'}:offline()
    if mode in {'install','check'}:
        if mode=='install' and request['provider']!='kokoro':
            from huggingface_hub import snapshot_download
            repo='ResembleAI/chatterbox' if request['provider']=='chatterbox' else 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'
            args={'repo_id':repo,'revision':REVISIONS[request['provider']],'local_dir':str(home/'model')}
            if request['provider']=='chatterbox':args['allow_patterns']=['ve.pt','s3gen.pt','t3_mtl23ls_v2.safetensors','grapheme_mtl_merged_expanded_v1.json','conds.pt','Cangjie5_TC.json','LICENSE*','README*']
            snapshot_download(**args)
            # CustomVoice repo includes speech_tokenizer/*; no second copy or implicit hub lookup.
        engine=load(request)
        voices=manifest(engine,request)
        if not voices:raise ValueError('Bộ TTS chưa có giọng.')
        # Verify real synthesis, not just import. Missing phonemizer/weights must fail install.
        opt={'language':'en-us' if request['provider']=='kokoro' else 'en','emotion':'neutral','intensity':.5,'instruction':''}
        preferred=next((r['id'] for r in voices if r.get('language')=='en-us' or r['id'].lower()=='ryan'),voices[0]['id'])
        command={'options':opt,'voice':preferred,'text':'Hello. This is a voice test.','output':str(home/'install-test.wav')}
        speak(engine,request,command)
        write(home/'voices.json',voices)
        # The installer runs check in a fresh, offline process (HF constants initialize at import time).
        print('TTS_RUNTIME_OK',flush=True);return
    engine=load(request)
    for line in sys.stdin:
        command=json.loads(line);done=Path(command['done'])
        try:speak(engine,request,command);write(done,{'ok':True})
        except Exception as exc:write(done,{'error':str(exc)[:1400]})

if __name__=='__main__':main(sys.argv[1],json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')))
