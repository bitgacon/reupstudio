"""Bounded CTC Viterbi alignment. No model imports or downloads here."""
import numpy as np


def align(log_probs, tokens, blank):
    p=np.asarray(log_probs,dtype=np.float32)
    if p.ndim!=2 or not np.isfinite(p).all() or not tokens or blank in tokens:
        raise ValueError('CTC: emission/token không hợp lệ.')
    if len(tokens)>3000 or p.shape[0]* (2*len(tokens)+1)>12_000_000:
        raise ValueError('CTC: đoạn quá lớn; chia audio/văn bản trước.')
    if min(tokens)<0 or max(tokens)>=p.shape[1] or not 0<=blank<p.shape[1]:raise ValueError('CTC: token ngoài vocabulary.')
    labels=np.full(2*len(tokens)+1,blank,dtype=int);labels[1::2]=tokens
    n=len(labels);prev=np.full(n,-np.inf,dtype=np.float32);prev[:2]=p[0,labels[:2]]
    back=np.zeros((len(p),n),dtype=np.uint8)
    skip=np.zeros(n,dtype=bool);skip[2:]=(labels[2:]!=blank)&(labels[2:]!=labels[:-2])
    for t in range(1,len(p)):
        one=np.r_[-np.inf,prev[:-1]];two=np.r_[-np.inf,-np.inf,prev[:-2]]
        two[~skip]=-np.inf
        choices=np.stack((prev,one,two));best=choices.argmax(axis=0)
        back[t]=best;prev=choices[best,np.arange(n)]+p[t,labels]
    state=n-1 if prev[-1]>=prev[-2] else n-2
    if not np.isfinite(prev[state]):raise ValueError('CTC: không đủ frame để căn toàn bộ lời; không tạo mốc giả.')
    path=np.empty(len(p),dtype=int)
    for t in range(len(p)-1,-1,-1):
        path[t]=state
        if t:state-=int(back[t,state])
    rows=[]
    for i,token in enumerate(tokens):
        frames=np.flatnonzero(path==2*i+1)
        if not len(frames):raise ValueError('CTC: thiếu mốc token.')
        rows.append({'start':int(frames[0]),'end':int(frames[-1])+1,
                     'confidence':float(np.exp(p[frames,token]).mean())})
    return rows


def word_rows(words, token_ranges, rows, duration_ms, frames):
    result=[]
    for word,(a,b) in zip(words,token_ranges):
        part=rows[a:b]
        if not part:raise ValueError('Từ không có token CTC.')
        start=round(part[0]['start']*duration_ms/frames);end=round(part[-1]['end']*duration_ms/frames)
        if end<=start:raise ValueError('Mốc từ quá ngắn; chưa thể áp dụng.')
        result.append({'word':word,'start':start,'end':end,'confidence':sum(r['confidence'] for r in part)/len(part)})
    return result
