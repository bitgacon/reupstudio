from uuid import uuid4
import threading
from PIL import Image
from reup import media,storage,timeline

def test_real_render_restricted_smooth_phase(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
    source=folder/'source.png';Image.new('RGB',(160,90),(255,0,0)).save(source)
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Red'})
    project=storage.new_project('Smooth cut');s=lambda u:u*u*(3-2*u)
    clip=timeline.Clip(id=uuid4().hex,asset=key,start_ms=0,duration_ms=1300,scale=.25,motion_easing='smooth',keyframes=[{'ms':0,'x':20+60*s(.35),'y':50,'ease_start':.35,'ease_end':1},{'ms':1300,'x':80,'y':50}])
    doc=timeline.Timeline(width=320,height=180,assets=[key],tracks=[timeline.Track(id=uuid4().hex,kind='video',name='Cut',clips=[clip])]).model_dump();saved=timeline.save(project['id'],doc)
    output=tmp_path/'cut.mp4';timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    for second in (.2,.6,1):
        frame=tmp_path/f'{second}.png';media.command([media.binary(),'-y','-v','error','-ss',str(second),'-i',str(output),'-frames:v','1',str(frame)])
        image=Image.open(frame).convert('RGB');xs=[x for y in range(180) for x in range(320) if image.getpixel((x,y))[0]>200]
        expected=320*(20+60*s((700+second*1000)/2000))/100
        assert abs(sum(xs)/len(xs)-expected)<5
