import threading
from uuid import uuid4

import pytest
from reup import storage, timeline, media, editor, project_transfer
from reup.workflows import Workflows, cue_key
from pydub import AudioSegment


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    media.configure_audio()


@pytest.fixture
def project(tmp_path):
    p=storage.new_project('Source')
    movie=tmp_path/'source.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=black:s=320x180:r=25:d=1',
        '-c:v','libx264',str(movie)])
    project_transfer.attach(p,movie)
    return p


def transfer(p,target,revision=None,event=None):
    revision=p['revision'] if revision is None else revision
    return project_transfer.run(Workflows(),{'project_id':p['id'],'target':target,'revision':revision,'confirmed':True},
        uuid4().hex,lambda *a:None,event or threading.Event())


def test_kinds_and_legacy_inference_do_not_migrate():
    dub=storage.new_project('Dub');edit=storage.new_project('Edit',kind='edit')
    assert {p['kind'] for p in storage.list_projects()}=={'dub','edit'}
    legacy={**dub};legacy.pop('kind');storage.atomic_json(storage.project_path(dub['id'])/'project.json',legacy)
    storage.atomic_json(timeline.path(dub['id']),timeline.Timeline().model_dump())
    assert storage.project_kind(legacy)=='edit'
    legacy['cues']=[{'id':1}];storage.atomic_json(storage.project_path(dub['id'])/'project.json',legacy)
    assert storage.project_kind(legacy)=='dub'
    doc=timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='Words',kind='text',clips=[])]).model_dump()
    storage.atomic_json(timeline.path(dub['id']),doc)
    assert storage.project_kind(legacy)=='hybrid'
    assert 'kind' not in storage.project(dub['id'])


def test_power_loss_transfer_copy_recovers_without_touching_original():
    original=storage.new_project('Original');snapshot=storage.project(original['id'])
    pending=storage.new_project('Incomplete copy',kind='edit',transfer_pending=True)
    assert len(storage.list_projects())==1
    assert storage.recover_pending_transfers()==[pending['id']]
    assert storage.recover_pending_transfers()==[]
    assert storage.list_projects(deleted=True)[0]['id']==pending['id']
    storage.delete_project(pending['id'],restore=True)
    assert len(storage.list_projects())==2 and not storage.project(pending['id']).get('transfer_pending')
    assert storage.project(original['id'])==snapshot


def test_dub_copy_then_editor_render_copy_preserve_original(project):
    p=project;p['cues']=[{'id':1,'start_ms':0,'end_ms':900,'text':'Hello','status':'pending'}]
    p['edit']=editor.config({'subtitle_style':'box','subtitle_box_color':'#ff0000','subtitle_box_opacity':.8,
        'title':'Title','title_box':True,'title_box_color':'#00ff00'})
    storage.save_project(p);before=storage.project(p['id'])
    result=transfer(p,'edit');new=storage.project(result['project_id']);doc=timeline.load(new['id'])
    assert new['kind']=='edit' and new['id']!=p['id'] and storage.project(p['id'])==before
    assert 'Chưa có audio' in result['message']
    text=[c for t in doc['tracks'] if t['kind']=='text' for c in t['clips']]
    assert text[0]['box_color']=='#ff0000' and text[0]['box_opacity']==.8
    assert text[1]['box_color']=='#00ff00'
    back=transfer(new,'dub',doc['revision']);dub=storage.project(back['project_id'])
    assert dub['kind']=='dub' and dub['cues']==[]
    source,_=storage.project_asset(dub,dub['video']);assert source.is_file()
    assert media.probe(source)['streams'][0]['width']==320
    assert storage.project(p['id'])==before


def test_completed_dub_audio_is_rendered_on_copy_only(project):
    p=project;p['voice']='test';p['cues']=[{'id':1,'start_ms':0,'end_ms':900,'text':'Hello',
        'status':'complete','audio':'1.wav','rate':1}]
    cue=p['cues'][0];cue['fingerprint']=cue_key(cue,p,storage.settings()['precision'],storage.reading_settings())
    folder=storage.project_path(p['id'])/'cues';folder.mkdir()
    AudioSegment.silent(duration=900).export(folder/'1.wav',format='wav')
    storage.save_project(p);before=storage.project(p['id'])
    result=transfer(p,'edit');assert 'Audio và hiệu ứng' in result['message']
    assert storage.project(p['id'])==before
    new=storage.project(result['project_id']);source,_=storage.project_asset(new,new['video'])
    assert any(s['codec_type']=='audio' for s in media.probe(source)['streams'])


def test_transfer_validation_and_cancel_do_not_create_copy(project):
    with pytest.raises(ValueError,match='thay đổi'):transfer(project,'edit',0)
    with pytest.raises(ValueError,match='thuộc'):transfer(project,'dub')
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):transfer(project,'edit',event=event)
    assert len(storage.list_projects())==1


def test_background_validation_and_presets():
    for patch in ({'title_box_color':'red'},{'subtitle_box_opacity':1.1}):
        with pytest.raises(ValueError):editor.config(patch)
    for patch in ({'box_color':'red'},{'box_opacity':-1}):
        with pytest.raises(ValueError):timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=100,**patch)
    preset=timeline.LayoutPreset(name='Color',kind='text',layout={'box':True,'box_color':'#123456','box_opacity':.25})
    assert preset.layout['box_color']=='#123456' and preset.layout['box_opacity']==.25


def test_title_background_real_libass(tmp_path):
    cfg=editor.config({'title':'TITLE','title_y':50,'title_box':True,'title_box_color':'#00ff00','title_box_opacity':1})
    editor.write_ass(tmp_path/'title.ass',[],cfg,320,180,1000,burn=False)
    frame=tmp_path/'title.ppm'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=black:s=320x180:d=1',
        '-vf','ass=title.ass','-frames:v','1',str(frame)],cwd=tmp_path)
    raw=frame.read_bytes().split(b'\n',3)[3]
    assert sum(g>r+100 and g>b+100 for r,g,b in zip(raw[::3],raw[1::3],raw[2::3]))>100


@pytest.mark.parametrize('opacity',[1,.5,0])
def test_real_ass_background_color_pixels(tmp_path,opacity):
    """Black canvas: red box, white glyphs. Test actual libass, not just the file."""
    clip=timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1000,text='TEST',font_size=50,
        box=True,box_color='#ff0000',box_opacity=opacity)
    doc=timeline.Timeline(width=320,height=180,tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[clip])])
    p=storage.new_project('Text',kind='edit');output=tmp_path/'text.mp4'
    timeline.render(p,doc.model_dump(),output,threading.Event(),lambda *a:None)
    frame=tmp_path/'frame.ppm'
    media.command([media.binary(),'-y','-v','error','-ss','0.5','-i',str(output),'-frames:v','1',str(frame)])
    raw=frame.read_bytes().split(b'\n',3)[3];pixels=list(zip(raw[::3],raw[1::3],raw[2::3]))
    red=[r for r,g,b in pixels if r>g+30 and r>b+30]
    if opacity==0:assert len(red)<20
    else:assert len(red)>100 and max(red)>=opacity*210
