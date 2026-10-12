import threading
from uuid import uuid4
from PIL import Image
import pytest
from reup import creative,timeline,storage,media
from reup.workflows import Workflows

def test_catalog_assets_and_numeric_validation():
    assert len(creative.catalog()['filters'])==8 and len(creative.catalog()['media'])==47
    for item in creative.catalog()['filters']+creative.catalog()['media']:
        path=storage.ROOT/'web'/'creative'/(item['id']+'.png');assert path.is_file();Image.open(path).verify()
    with pytest.raises(ValueError):timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=100,color_filter='movie;inject')
    with pytest.raises(ValueError):timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=100,filter_strength=float('nan'))
    assert creative.matrix('mono',0)==creative.FILTERS['none'][1]

@pytest.mark.parametrize('kind',['mono','sepia','warm','cool','cinema','neon','dream'])
def test_real_filter_matches_rgb_matrix(tmp_path,monkeypatch,kind):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.png';Image.new('RGB',(160,90),(80,120,160)).save(source)
    storage.atomic_json(folder/'asset.json',{'id':key,'name':'Color','file':source.name});project=storage.new_project('Filter')
    doc=timeline.Timeline(width=160,height=90,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Filter',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=key,start_ms=0,duration_ms=500,color_filter=kind,filter_strength=.65)])]).model_dump()
    saved=timeline.save(project['id'],doc);output=tmp_path/'filter.mp4';timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    frame=tmp_path/'frame.png';media.command([media.binary(),'-y','-v','error','-i',str(output),'-frames:v','1',str(frame)])
    rgb=Image.open(frame).convert('RGB').getpixel((80,45));m=creative.matrix(kind,.65);expected=[sum(m[3*i+j]*[80,120,160][j] for j in range(3)) for i in range(3)]
    assert all(abs(a-b)<8 for a,b in zip(rgb,expected)),(rgb,expected)

def test_sticker_and_magic_render_preserve_alpha_and_credits(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();project=storage.new_project('Creative');flow=Workflows();event=threading.Event()
    sticker=flow.job_editor_creative({'project_id':project['id'],'creative_id':'heart'},uuid4().hex,lambda *a:None,event)['media']
    magic=flow.job_editor_creative({'project_id':project['id'],'creative_id':'magic-ring'},uuid4().hex,lambda *a:None,event)['media'];assert magic['alpha_video'] and 2980<=magic['duration_ms']<=3040
    source,meta=storage.project_asset(project,sticker['id']);assert 'CC BY 4.0' in meta['attribution'];assert Image.open(source).getchannel('A').getextrema()==(0,255)
    doc=timeline.Timeline(width=160,height=90,assets=[sticker['id'],magic['id']],tracks=[timeline.Track(id=uuid4().hex,name='Heart',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=sticker['id'],start_ms=0,duration_ms=500,scale=.5)]),timeline.Track(id=uuid4().hex,name='Magic',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=magic['id'],start_ms=0,duration_ms=500)])]).model_dump();saved=timeline.save(project['id'],doc)
    result=flow.job_editor_export({'project_id':project['id'],'revision':saved['revision']},uuid4().hex,lambda *a:None,event);assert len(result['files'])==2 and result['files'][1]['name']=='ATTRIBUTION.txt'
    assert creative.magic_frame('magic-ring',0).tobytes()!=creative.magic_frame('magic-ring',.5).tobytes()

@pytest.mark.parametrize('kind',list(creative.MAGIC))
def test_original_effect_frames(kind):
    image=creative.magic_frame(kind,.7);assert image.mode=='RGBA'
    low,high=image.getchannel('A').getextrema();assert low==0 and high>0
    assert image.tobytes()!=creative.magic_frame(kind,1.3).tobytes()
    assert creative.magic_frame(kind,.7,160).size==(160,160)

@pytest.mark.parametrize('kind',['fluent-3D-heart','fluent-Flat-love','magic-aurora','magic-hologram','magic-speed'])
def test_new_media_real_job(tmp_path,monkeypatch,kind):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();project=storage.new_project('Extended creative')
    result=creative.make_media(project,kind,tmp_path/'job',threading.Event(),lambda *a:None)
    source,meta=storage.project_asset(project,result['id'])
    assert meta['creative_id']==kind and (tmp_path/'job'/'ATTRIBUTION.txt').is_file()
    if kind in creative.FLUENT:
        assert 'MIT License' in meta['attribution'] and 'Microsoft' in meta['attribution']
        assert Image.open(source).getchannel('A').getextrema()[0]==0
    else:assert result['alpha_video'] and 2980<=result['duration_ms']<=3040
