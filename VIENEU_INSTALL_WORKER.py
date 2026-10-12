"""Download only on explicit install; verify synthesis again offline before registration."""
import os,sys
from pathlib import Path
mode,raw,precision=sys.argv[1:4]
home=Path(raw);os.environ['HF_HOME']=str(home/'models_cache')
os.environ['VIENEU_BACKEND']='onnx';os.environ['VIENEU_DEVICE']='cpu'
if mode=='check':os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
elif mode!='install':raise ValueError('Unsupported mode')
from vieneu import Vieneu
engine=Vieneu(backend='onnx',device='cpu',precision=precision)
audio=engine.infer('Xin chào, đây là câu kiểm tra giọng đọc.')
engine.save(audio,str(home/'install-test.wav'))
if not (home/'install-test.wav').is_file() or (home/'install-test.wav').stat().st_size<44:raise ValueError('No audio')
from apps.openai_speech import app
print('VIENEU_READY',flush=True)
