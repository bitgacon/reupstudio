"""Adapter for official portable VSR 1.1.1; never edits its code or user's source."""
import json
import sys
import traceback
import math
from pathlib import Path


def load(home):
    sys.path.insert(0,str(home));sys.path.insert(0,str(home/'backend'))
    import config
    import backend
    # Upstream mixes `import config` and `from backend import config`.
    # Share one module, otherwise MODE/device changes only reach half the code.
    sys.modules['backend.config']=config
    backend.config=config
    from backend.main import SubtitleRemover
    return SubtitleRemover,config


def main():
    if sys.argv[1]=='--check':
        load(Path(sys.argv[2]));print('VSR_LEGACY_RUNTIME_OK');return
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    cls,config=load(Path(request['home']))
    failures=[]
    status={'region':0,'done':0,'total':1}
    def report(frames):
        fraction=(status['region']+min(1,frames/status['total']))/len(request['areas'])*100
        print(f'REUP_VSR_PROGRESS={fraction:.4f}',flush=True)
    module=sys.modules.get('backend.inpaint.sttn_inpaint')
    inpaint_class=getattr(module,'STTNInpaint',None)
    if inpaint_class:
        original=inpaint_class.inpaint
        def checked_inpaint(self,*args,**kwargs):
            infer=self.model.infer
            steps=max(1,math.ceil(len(args[0])/self.neighbor_stride));completed=0
            def tracked_infer(*a,**kw):
                nonlocal completed
                result=infer(*a,**kw);completed+=1
                report(status['done']+len(args[0])*completed/steps*.95)
                return result
            self.model.infer=tracked_infer
            try:return original(self,*args,**kwargs)
            except Exception as exc:
                traceback.print_exc();failures.append(str(exc));raise
            finally:self.model.infer=infer
        inpaint_class.inpaint=checked_inpaint
    device=request.get('device','cpu')
    if device not in {'cpu','auto'}:raise ValueError('Invalid VSR device')
    source=Path(request['source']);output=Path(request['output'])
    intermediates=[]
    for i,area in enumerate(request['areas']):
        target=output if i==len(request['areas'])-1 else output.with_name(f'vsr-region-{i}.mp4')
        remover=cls(str(source),sub_area=tuple(area),gui_mode=False)
        status.update(region=i,done=0,total=max(1,getattr(remover,'frame_count',1)))
        update=getattr(remover,'update_progress',None)
        if update:
            def tracked_update(tbar,increment):
                update(tbar,increment)
                status['done']+=increment
                report(status['done'])
            remover.update_progress=tracked_update
        # Constructor reloads config. Apply only after construction; do not edit config.py.
        config.MODE=config.InpaintMode.STTN;config.STTN_SKIP_DETECTION=True
        if device=='cpu':
            import torch
            torch.set_num_threads(2)
            config.USE_DML=False;config.device=torch.device('cpu')
        print('REUP_VSR_DEVICE='+device,flush=True)
        remover.video_out_name=str(target)
        remover.run()
        if failures:raise RuntimeError('VSR model failed: '+failures[0])
        if not target.is_file() or not target.stat().st_size:raise RuntimeError('VSR did not produce region output')
        report(status['total'])
        if source in intermediates:source.unlink()
        source=target
        if target!=output:intermediates.append(target)
    print('VSR_LEGACY_FINISHED')


if __name__=='__main__':main()
