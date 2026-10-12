"""Conservative template-tracking policy. No identity or occlusion AI claims."""
import math

class TrackingPolicy:
    def __init__(self,max_gap_ms=1000):
        self.max_gap_ms=max_gap_ms;self.center=None;self.lost_at=None;self.rows=[];self.stopped=None

    def update(self,ms,center,confidence,scene_change=False):
        if self.stopped:return False
        if scene_change and self.center is not None:
            self.stopped={'ms':ms,'reason':'scene_cut'};return False
        confident=math.isfinite(confidence) and confidence>=.65 and all(math.isfinite(v) and 0<=v<=1 for v in center)
        if self.center is None:
            if not confident:raise ValueError('Mẫu đầu không đủ rõ để tracking.')
            self.center=list(center)
        elif not confident:
            if self.lost_at is None:self.lost_at=ms
            if ms-self.lost_at>=self.max_gap_ms:
                self.stopped={'ms':self.lost_at,'reason':'lost_too_long'};return False
        else:
            self.center=list(center);self.lost_at=None
        self.rows.append({'ms':ms,'center':list(self.center),'confidence':float(confidence) if math.isfinite(confidence) else 0,
                          'state':'tracked' if confident else 'held'})
        return True

    def result(self,duration_ms):
        end=self.stopped['ms'] if self.stopped else duration_ms
        rows=[r for r in self.rows if r['ms']<=end]
        if end<100 or not rows:raise ValueError('Tracking quá ngắn; chọn lại vùng rõ hơn.')
        if rows[-1]['ms']<end:rows.append({**rows[-1],'ms':end})
        return {'rows':rows,'duration_ms':end,'stopped':self.stopped,
                'held_samples':sum(r['state']=='held' for r in rows)}
