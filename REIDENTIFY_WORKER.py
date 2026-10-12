"""Appearance reacquisition, optional local ONNX ReID encoder (NCHW 256x128)."""
import cv2,numpy as np
from REIDENTIFY_POLICY import ReidentifyPolicy

def track(request,progress):
    cap=cv2.VideoCapture(request['source']);policy=ReidentifyPolicy();template=None;histogram=None;reference=None;session=None
    if request.get('reid_model'):
        import onnxruntime as ort
        session=ort.InferenceSession(request['reid_model'],providers=['CPUExecutionProvider'])
        inputs=session.get_inputs()
        if len(inputs)!=1 or inputs[0].type!='tensor(float)' or len(inputs[0].shape)!=4 or inputs[0].shape[1:]!=[3,256,128]:raise ValueError('ReID ONNX cần 1 input float NCHW [1,3,256,128], output vector embedding.')
    def embedding(image):
        image=cv2.cvtColor(cv2.resize(image,(128,256)),cv2.COLOR_BGR2RGB).astype(np.float32)/255
        tensor=((image-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)).transpose(2,0,1)[None]
        result=np.asarray(session.run(None,{session.get_inputs()[0].name:tensor})[0]).reshape(-1)
        if not 16<=len(result)<=4096 or not np.isfinite(result).all() or np.linalg.norm(result)<1e-8:raise ValueError('Output ONNX không phải embedding hợp lệ.')
        return result/np.linalg.norm(result)
    try:
        for i,sample in enumerate(request['samples']):
            cap.set(cv2.CAP_PROP_POS_MSEC,sample['source_ms']);ok,frame=cap.read()
            if not ok:raise ValueError('Không đọc được frame ReID.')
            h,w=frame.shape[:2];factor=min(1,640/max(w,h));frame=cv2.resize(frame,(round(w*factor),round(h*factor)));gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY);H,W=gray.shape
            hist=np.histogram(gray,bins=32,range=(0,256))[0].astype(float);hist/=max(1,hist.sum());scene=histogram is not None and abs(hist-histogram).sum()>.9;histogram=hist
            if template is None:
                bx,by,bw,bh=request['box'];x=round(bx*W);y=round(by*H);bw=max(8,round(bw*W));bh=max(8,round(bh*H));template=gray[y:y+bh,x:x+bw].copy()
                if template.shape!=(bh,bw) or template.std()<4:raise ValueError('Chọn vùng có chi tiết.')
                if session:reference=embedding(frame[y:y+bh,x:x+bw])
                score=margin=1.
            else:
                scores=cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED)
                candidates=[];work=scores.copy()
                for _ in range(12):
                    _,value,_,(cx,cy)=cv2.minMaxLoc(work)
                    if value<-1:break
                    appearance=float(np.dot(reference,embedding(frame[cy:cy+bh,cx:cx+bw]))) if session else float(value)
                    candidates.append((appearance,cx,cy))
                    work[max(0,cy-bh//2):min(len(work),cy+bh//2+1),max(0,cx-bw//2):min(work.shape[1],cx+bw//2+1)]=-2
                candidates.sort(reverse=True);score,x,y=candidates[0];margin=score-(candidates[1][0] if len(candidates)>1 else -1)
            policy.update(sample['ms'],[(x+bw/2)/W,(y+bh/2)/H],score,margin,scene)
            progress(5+90*(i+1)/len(request['samples']),'Tái tìm ngoại hình; lớp ẩn trong đoạn mất dấu…')
    finally:cap.release()
    result=policy.result(request['samples'][-1]['ms']);result['method']='onnx-reid' if session else 'global-template';return result
