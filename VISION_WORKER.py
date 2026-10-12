"""Isolated CPU worker. Only accepts app-generated local request JSON."""
import json
import os
from pathlib import Path
import subprocess
import sys

def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value),encoding='utf-8');os.replace(tmp,path)

def main(request):
    folder=Path(request['folder']);source=request['source']
    def progress(p,message):write(folder/'progress.json',{'percent':p,'message':message})
    if request['kind']=='reidentify':
        from REIDENTIFY_WORKER import track
        write(folder/'result.json',track(request,progress));return
    if request['kind']=='object':
        import cv2
        from TRACKING_POLICY import TrackingPolicy
        import numpy as np
        cap=cv2.VideoCapture(source);template=None;previous=None;histogram=None;policy=TrackingPolicy()
        try:
            for i,sample in enumerate(request['samples']):
                cap.set(cv2.CAP_PROP_POS_MSEC,sample['source_ms']);ok,frame=cap.read()
                if not ok:raise RuntimeError('Không đọc được frame tracking.')
                h,w=frame.shape[:2];factor=min(1,640/max(w,h));small=cv2.resize(frame,(round(w*factor),round(h*factor)));gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY);H,W=gray.shape
                hist=np.histogram(gray,bins=32,range=(0,256))[0].astype(float);hist/=max(1,hist.sum())
                scene_change=histogram is not None and abs(hist-histogram).sum()>.9
                histogram=hist
                if template is None:
                    x,y,bw,bh=request['box'];x=round(x*W);y=round(y*H);bw=max(8,round(bw*W));bh=max(8,round(bh*H))
                    template=gray[y:y+bh,x:x+bw].copy();previous=(x,y)
                    if template.shape!=(bh,bw) or template.std()<4:raise ValueError('Chọn vùng có chi tiết, nằm trong hình.')
                    score=1
                else:
                    px,py=previous;radius=max(bw,bh,80);left=max(0,px-radius);top=max(0,py-radius);right=min(W,px+bw+radius);bottom=min(H,py+bh+radius)
                    scores=cv2.matchTemplate(gray[top:bottom,left:right],template,cv2.TM_CCOEFF_NORMED);_,score,_,where=cv2.minMaxLoc(scores);x=left+where[0];y=top+where[1]
                    if score>=.65 and not scene_change:previous=(x,y)
                if not policy.update(sample['ms'],[(x+bw/2)/W,(y+bh/2)/H],float(score),scene_change):break
                progress(5+90*(i+1)/len(request['samples']),'Đang bám vùng; giữ vị trí khi che khuất ngắn…')
        finally:cap.release()
        write(folder/'result.json',policy.result(request['samples'][-1]['ms']));return
    if request['kind']=='face':
        import cv2
        model=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        if model.empty():raise RuntimeError('Thiếu model nhận dạng mặt OpenCV.')
        cap=None if request['image'] else cv2.VideoCapture(source)
        rows=[];previous=None
        try:
            for i,sample in enumerate(request['samples']):
                if cap is None:
                    import numpy as np
                    frame=cv2.imdecode(np.fromfile(source,dtype=np.uint8),cv2.IMREAD_COLOR)
                else:cap.set(cv2.CAP_PROP_POS_MSEC,sample['source_ms']);ok,frame=cap.read();frame=frame if ok else None
                center=None
                if frame is not None:
                    h,w=frame.shape[:2];factor=min(1,640/max(w,h));small=cv2.resize(frame,(max(1,round(w*factor)),max(1,round(h*factor))))
                    gray=cv2.equalizeHist(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY));faces=model.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5,minSize=(24,24))
                    candidates=[((x+fw/2)/small.shape[1],(y+fh/2)/small.shape[0],fw*fh) for x,y,fw,fh in faces]
                    if candidates:
                        chosen=max(candidates,key=lambda f:f[2]) if previous is None else min(candidates,key=lambda f:(f[0]-previous[0])**2+(f[1]-previous[1])**2)
                        center=list(chosen[:2]);previous=center
                rows.append({'ms':sample['ms'],'face':center});progress(5+90*(i+1)/len(request['samples']),'Đang dò mặt theo mẫu…')
        finally:
            if cap is not None:cap.release()
        write(folder/'result.json',{'rows':rows});return
    if request['kind']!='background':raise ValueError('Tác vụ không hỗ trợ.')
    from PIL import Image
    from rembg import new_session,remove
    progress(5,'Nạp U2NetP; lần đầu tải model nhỏ…')
    session=new_session('u2netp',providers=['CPUExecutionProvider'])
    if request['image']:
        with Image.open(source) as image:
            image=image.convert('RGB');image.thumbnail((1536,1536));remove(image,session=session).save(folder/'background.png')
        write(folder/'result.json',{'file':'background.png'});return
    # Bounded raw streaming, no temporary full-frame sequence on disk.
    import cv2
    cap=cv2.VideoCapture(source);w=cap.get(cv2.CAP_PROP_FRAME_WIDTH);h=cap.get(cv2.CAP_PROP_FRAME_HEIGHT);cap.release()
    if w<=0 or h<=0:raise RuntimeError('Không đọc được kích thước video.')
    factor=min(1,720/max(w,h));w=max(2,int(w*factor)//2*2);h=max(2,int(h*factor)//2*2);fps=12
    output=folder/'background.webm';frames=max(1,round(request['seconds']*fps))
    with (folder/'ffmpeg.log').open('w') as log:
        dec=subprocess.Popen([request['ffmpeg'],'-v','error','-ss',str(request['start']),'-i',source,'-t',str(request['seconds']),'-vf',f'scale={w}:{h},fps={fps}','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=log)
        enc=subprocess.Popen([request['ffmpeg'],'-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-auto-alt-ref','0','-threads','2',str(output)],stdin=subprocess.PIPE,stderr=log,stdout=log)
        try:
            count=0;size=w*h*3
            while True:
                data=bytearray()
                while len(data)<size:
                    part=dec.stdout.read(size-len(data))
                    if not part:break
                    data.extend(part)
                if not data:break
                if len(data)!=size:raise RuntimeError('Frame video không đầy đủ.')
                frame=remove(Image.frombytes('RGB',(w,h),bytes(data)),session=session).convert('RGBA');enc.stdin.write(frame.tobytes());count+=1
                progress(10+85*min(1,count/frames),'Đang tách nền từng frame trên CPU…')
            enc.stdin.close()
            if dec.wait()!=0 or enc.wait()!=0 or not count:raise RuntimeError('FFmpeg tách nền lỗi; xem ffmpeg.log.')
        finally:
            for proc in (dec,enc):
                if proc.poll() is None:proc.kill();proc.wait()
    write(folder/'result.json',{'file':output.name})

if __name__=='__main__':main(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
