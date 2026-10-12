"""Reacquisition gate: never draw during uncertain gaps, two consistent hits."""
import math

class ReidentifyPolicy:
    def __init__(self):self.center=None;self.pending=None;self.rows=[]
    def update(self,ms,center,score,margin,scene_change=False):
        confident=math.isfinite(score) and score>=.88 and math.isfinite(margin) and margin>=.06 and all(math.isfinite(v) and 0<=v<=1 for v in center)
        if not self.rows:
            if not confident:raise ValueError('Mẫu đầu chưa đủ rõ.')
            self.center=list(center);visible=True;state='tracked'
        elif scene_change or not confident:
            self.pending=None;visible=False;state='lost'
        elif self.rows[-1]['visible']:
            self.center=list(center);visible=True;state='tracked'
        elif self.pending and math.dist(self.pending,center)<.15:
            self.center=list(center);self.pending=None;visible=True;state='reacquired'
        else:self.pending=list(center);visible=False;state='confirming'
        self.rows.append({'ms':ms,'center':list(self.center),'confidence':float(score),'margin':float(margin),'state':state,'visible':visible})

    def result(self,duration_ms):
        segments=[];start=None
        for i,row in enumerate(self.rows):
            if row['visible'] and start is None:start=i
            end=self.rows[i+1]['ms'] if i+1<len(self.rows) else duration_ms
            if start is not None and (i+1==len(self.rows) or not self.rows[i+1]['visible']):
                a=self.rows[start]['ms'];part=self.rows[start:i+1]
                if end-a>=100:
                    segments.append({'start':a,'end':end,'rows':part+([{**part[-1],'ms':end}] if part[-1]['ms']<end else [])})
                start=None
        if not segments:raise ValueError('Không có đoạn bám chắc chắn đủ 100ms.')
        return {'rows':self.rows,'segments':segments,'duration_ms':duration_ms,'held_samples':0,
                'reacquired_samples':sum(r['state']=='reacquired' for r in self.rows)}
