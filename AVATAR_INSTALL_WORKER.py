"""Explicit MuseTalk dependency/model checks in its private Python environment."""
import hashlib,json,os,shutil,sys
from pathlib import Path
from reup.avatar_manifest import MODELS


def verify(path,size,algorithm,digest):
    path=Path(path)
    if not path.is_file() or path.stat().st_size!=size:raise ValueError('Model thiếu/sai kích thước: '+path.name)
    h=hashlib.sha256() if algorithm=='sha256' else hashlib.sha1()
    if algorithm=='git-sha1':h.update(f'blob {size}\0'.encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=digest:raise ValueError('Checksum model không khớp: '+path.name)


def probe(home):
    import torch,cv2,mmcv,mmdet,mmpose
    import mmcv.ops
    if not torch.cuda.is_available():raise ValueError('MuseTalk cần GPU NVIDIA CUDA hoạt động.')
    x=torch.ones((2,2),device='cuda');float((x@x).sum().item())
    if home:
        os.chdir(home);sys.path.insert(0,str(home));import scripts.inference
    return {'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
        'vram_bytes':torch.cuda.get_device_properties(0).total_memory}


def main():
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));home=Path(request['home'])
    if request['mode']=='probe':report=probe(None)
    elif request['mode'] in {'models','check'}:
        for repo,revision,name,target,size,algorithm,digest in MODELS:
            destination=home/'models'/target
            if request['mode']=='models':
                from huggingface_hub import hf_hub_download
                print('MODEL '+name,flush=True)
                cached=Path(hf_hub_download(repo_id=repo,revision=revision,filename=name,
                    cache_dir=request['cache'],endpoint='https://huggingface.co'))
                verify(cached,size,algorithm,digest)
                destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(cached,destination)
            verify(destination,size,algorithm,digest)
        report=probe(home)
    else:raise ValueError('Chế độ cài avatar không hợp lệ.')
    Path(request['result']).write_text(json.dumps(report),encoding='utf-8');print('AVATAR_RUNTIME_OK',flush=True)


if __name__=='__main__':main()
