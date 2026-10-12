"""Optional OpenCV processing, no model downloads. Invoked by an owned job."""
import json, subprocess, sys
from pathlib import Path

def frame(image,areas,mode,radius):
    import cv2, numpy as np
    mask=np.zeros(image.shape[:2],dtype=np.uint8)
    for a,b,c,d in areas:mask[a:b,c:d]=255
    result=cv2.inpaint(image,mask,float(radius),cv2.INPAINT_NS if mode=='navier-stokes' else cv2.INPAINT_TELEA)
    if mode=='smooth':
        smooth=cv2.GaussianBlur(result,(3,3),0)
        result[mask>0]=smooth[mask>0]
    return result

def main():
    import cv2,numpy as np
    r=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));ff=r['ffmpeg'];folder=Path(r['output']).parent
    args=[ff,'-v','error','-noautorotate']
    if r['seconds'] is not None:args+=['-ss',str(r['seconds'])]
    args+=['-i',r['source']]
    with (folder/'decode.log').open('wb') as decode_log,(folder/'encode.log').open('wb') as encode_log:
        decoder=subprocess.Popen(args+['-map','0:v:0','-an','-f','rawvideo','-pix_fmt','bgr24','-threads','1','pipe:1'],stdout=subprocess.PIPE,stderr=decode_log)
        encoder=None;done=0
        try:
            if r['seconds'] is None:
                cmd=[ff,'-y','-v','error','-f','rawvideo','-pix_fmt','bgr24','-s',f"{r['width']}x{r['height']}",'-r',r['fps'],'-i','pipe:0']
                if r['keep_audio']:cmd+=['-i',r['source'],'-map','0:v:0','-map','1:a:0?','-c:a','aac']
                cmd+=['-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-threads','2','-t',str(r['duration']),'-movflags','+faststart',r['output']]
                encoder=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=encode_log)
            size=r['width']*r['height']*3
            while True:
                raw=decoder.stdout.read(size)
                if not raw:break
                if len(raw)!=size:raise RuntimeError('Truncated decoded frame')
                image=frame(np.frombuffer(raw,dtype=np.uint8).reshape(r['height'],r['width'],3),r['areas'],r['mode'],r['radius'])
                if encoder:encoder.stdin.write(image.tobytes())
                else:
                    if not cv2.imwrite(r['output'],image):raise RuntimeError('Cannot write preview')
                    break
                done+=1
                numerator,denominator=map(int,r['fps'].split('/')) if '/' in r['fps'] else (float(r['fps']),1)
                if done==1 or done%10==0:print('REUP_VSR_PROGRESS='+str(min(99,done*denominator/numerator/r['duration']*100)),flush=True)
            if encoder:
                encoder.stdin.close()
                if encoder.wait():raise RuntimeError('Encode failed; see encode.log')
                if decoder.wait():raise RuntimeError('Decode failed; see decode.log')
        finally:
            for process in (decoder,encoder):
                if process and process.poll() is None:process.terminate();process.wait()
            decoder.stdout.close()
        if not Path(r['output']).is_file() or not Path(r['output']).stat().st_size:raise RuntimeError('No output frames')
    print('REUP_VSR_PROGRESS=100',flush=True)

if __name__=='__main__':main()
