"""Opt-in model installer; publish only after speech + offline checks."""
import shutil
from . import storage,libraries

KOKORO_ASSETS=[
    {'name':'kokoro-v1.0.onnx','bytes':325505369,'sha256':'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a'},
    {'name':'voices-v1.0.bin','bytes':28214398,'sha256':'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'}]

def install(key,folder,log,event,progress):
    from .tts_providers import config
    provider=key.removeprefix('tts-')
    if provider not in {'kokoro','chatterbox','qwen'}:raise ValueError('Bộ TTS local không hợp lệ.')
    if event.is_set():raise InterruptedError('Đã dừng cài TTS.')
    required={'kokoro':2_000_000_000,'chatterbox':12_000_000_000,'qwen':15_000_000_000}[provider]
    if shutil.disk_usage(folder.parent).free<required:raise ValueError('Không đủ chỗ trống để cài '+provider+'.')
    # A new candidate must pass checks before replacing the registry. Never mutate the active runtime.
    python=libraries.environment(folder,log,event,progress)
    device=config()['device']
    if provider=='kokoro':
        libraries.run([str(python),'-m','pip','install','--disable-pip-version-check','kokoro-onnx==0.6.1','soundfile==0.13.1'],folder,log,event,progress)
        for i,row in enumerate(KOKORO_ASSETS):
            libraries.download({**row,'label':row['name'],'url':'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'+row['name']},folder/row['name'],event,lambda p,m:progress(20+i*20+p/3,m))
    else:
        index='https://download.pytorch.org/whl/cu124' if device=='cuda' else 'https://download.pytorch.org/whl/cpu'
        libraries.run([str(python),'-m','pip','install','torch==2.6.0','torchaudio==2.6.0','--index-url',index],folder,log,event,progress)
        package='chatterbox-tts==0.1.7' if provider=='chatterbox' else 'qwen-tts==0.1.1'
        libraries.run([str(python),'-m','pip','install','--disable-pip-version-check',package,'soundfile==0.13.1'],folder,log,event,progress)
    request={'provider':provider,'path':str(folder),'device':device};path=folder/'install-request.json';storage.atomic_json(path,request)
    progress(70,'Tải/kiểm tra model và tạo câu thử; chưa có % tải model chính xác…')
    libraries.run([str(python),str(storage.ROOT/'TTS_PROVIDER_WORKER.py'),'install',str(path)],folder,log,event,progress)
    libraries.run([str(python),str(storage.ROOT/'TTS_PROVIDER_WORKER.py'),'check',str(path)],folder,log,event,progress)
    if 'TTS_RUNTIME_OK' not in log.read_text(encoding='utf-8',errors='replace') or not (folder/'voices.json').is_file():raise ValueError('TTS chưa vượt kiểm tra tạo audio/offline; chưa kích hoạt.')
    return {'path':str(folder),'python':str(python),'provider':provider}
