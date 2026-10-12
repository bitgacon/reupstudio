"""VSR bridge acceptance uses a stdlib fake CLI, not an AI quality benchmark."""
import hashlib
from pathlib import Path
import shutil
import sys
import threading
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from reup import downloads, media, storage, subtitle_removal as vsr, timeline
from reup.server import make_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path / 'data')
    storage.DATA.mkdir()


def sample(tmp_path, audio=True):
    path = tmp_path / 'source.mp4'
    args = [media.binary(), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=160x90:r=25:d=1']
    if audio:
        args += ['-f', 'lavfi', '-i', 'sine=f=440:d=1', '-c:a', 'aac']
    media.command(args + ['-c:v', 'libx264', '-t', '1', str(path)])
    return path


def test_forget_subtitle_keeps_files_and_other_entries(tmp_path):
    key=uuid4().hex;other=uuid4().hex
    file=tmp_path/'original.srt';file.write_text('keep')
    path=storage.DATA/'vsr-subtitles.json'
    storage.atomic_json(path,[{'job_id':key,'subtitle':{'url':str(file)}},{'job_id':other}])
    vsr.forget_subtitle(key)
    assert storage.read_json(path)==[{'job_id':other}]
    assert file.read_text()=='keep'
    with pytest.raises(ValueError):vsr.forget_subtitle(key)


def test_forget_subtitle_api_requires_token(tmp_path):
    key=uuid4().hex;path=storage.DATA/'vsr-subtitles.json'
    storage.atomic_json(path,[{'job_id':key}])
    with TestClient(make_app()) as client:
        client.get('/')
        url='/api/subtitle-removal/subtitles/'+key+'/delete'
        assert client.post(url,json={}).status_code==403
        token=client.get('/api/state').json()['csrf']
        assert client.post(url,json={},headers={'X-Reup-Token':token}).status_code==200
    assert storage.read_json(path)==[]


def test_worker_progress_monotonic(tmp_path):
    script=tmp_path/'worker.py'
    script.write_text("import time\nfor p in [10,30,20,90,100]:\n print('REUP_VSR_PROGRESS='+str(p),flush=True);time.sleep(.4)\n")
    values=[]
    vsr.run_worker([sys.executable,str(script)],tmp_path,tmp_path/'log.txt',threading.Event(),lambda p,m:values.append(p),model_progress=True)
    assert values==sorted(values) and len(set(values))>=3
    assert max(values)<=88 and min(values)>=40


def engine(tmp_path):
    home = tmp_path / 'VSR folder with spaces'
    (home / 'backend' / 'tools').mkdir(parents=True)
    (home / 'backend' / 'tools' / 'args_handler.py').write_text('# --subtitle-area-coords --inpaint-mode', encoding='utf-8')
    (home / 'backend' / 'main.py').write_text('''import argparse,shutil
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('-i',required=True)
p.add_argument('-o',required=True)
p.add_argument('--inpaint-mode')
p.add_argument('--subtitle-area-coords','-c',nargs=4,action='append')
a=p.parse_args()
assert (Path(a.o).parent/'original.srt').is_file(), 'SRT must exist BEFORE VSR'
assert len(a.subtitle_area_coords)==2
shutil.copy2(a.i,a.o)
''', encoding='utf-8')
    vsr.config({'home': str(home), 'python': sys.executable})
    return home


def srt_asset(tmp_path):
    path = tmp_path / 'source.srt'
    path.write_text('1\n00:00:00,100 --> 00:00:00,800\nXin chào\n', encoding='utf-8')
    return vsr.store_asset(path, 'Phụ đề gốc.srt')


REGIONS = [{'x': 10, 'y': 70, 'w': 80, 'h': 20}, {'x': 1, 'y': 1, 'w': 20, 'h': 20}]


def test_coordinate_order_and_multiple_regions():
    coords = vsr.rectangles(REGIONS, 1920, 1080)
    assert coords[0] == [756, 972, 192, 1728]
    args = vsr.command(Path('root'), Path('python.exe'), Path('main.py'), Path('input with spaces.mp4'), Path('output.mp4'), 'sttn-auto', coords)
    assert args.count('-c') == 2
    assert args[args.index('-c')+1:args.index('-c')+5] == ['756', '972', '192', '1728']
    assert 'input with spaces.mp4' in args


@pytest.mark.parametrize('regions', [[], [dict(x=90, y=0, w=11, h=1)], [dict(x=float('nan'), y=0, w=1, h=1)], [dict(x=0, y=0, w=0, h=2)], REGIONS*7])
def test_bad_regions(regions):
    with pytest.raises(ValueError):
        vsr.rectangles(regions, 1920, 1080)


def test_not_ready_and_old_cli(tmp_path):
    assert vsr.status()['connected'] is False
    with pytest.raises(ValueError, match='Chưa kết nối'):
        vsr.runtime()
    home = engine(tmp_path)
    assert vsr.status()['connected']
    (home / 'backend' / 'tools' / 'args_handler.py').write_text('old CLI')
    assert vsr.status()['connected'] is False
    with pytest.raises(ValueError):
        vsr.config({'python': 'relative/python.exe'})
    with pytest.raises(ValueError):
        vsr.config({'command': 'arbitrary shell'})


def test_fake_cli_real_ffmpeg_preserves_source_srt_audio_and_transfer(tmp_path):
    engine(tmp_path)
    source = sample(tmp_path)
    key = vsr.store_asset(source, 'Nguồn.mp4')
    old = hashlib.sha256(storage.asset(key)[0].read_bytes()).hexdigest()
    sub = srt_asset(tmp_path)
    payload = {'asset': key, 'subtitle_mode': 'import', 'subtitle_asset': sub, 'regions': REGIONS}
    result = vsr.remove(payload, uuid4().hex, lambda *a: None, threading.Event())
    row = result['entry']
    assert old == hashlib.sha256(storage.asset(key)[0].read_bytes()).hexdigest()
    assert row['source_asset'] == key and row['asset'] != key
    assert storage.asset(row['subtitle_asset'])[0].read_bytes() == storage.asset(sub)[0].read_bytes()
    assert len(result['files']) == 2
    assert any(s['codec_type'] == 'audio' for s in media.probe(storage.asset(row['asset'])[0])['streams'])
    assert downloads.referenced(key)
    dub = vsr.send(row['id'], 'dub')
    value = storage.project(dub['project_id'])
    assert value['video'] == row['asset'] and value['cues'][0]['source_text'] == 'Xin chào'
    edit = vsr.send(row['id'], 'edit')
    doc = timeline.load(edit['project_id'])
    assert (doc['width'], doc['height']) == (160, 90)
    assert doc['tracks'][1]['clips'][0]['start_ms'] == 100
    assert doc['tracks'][1]['clips'][0]['duration_ms'] == 700
    assert timeline.save(edit['project_id'], doc)['tracks'][0]['clips'][0]['asset'] == row['asset']


def test_srt_failure_prevents_cli_and_keeps_source(tmp_path, monkeypatch):
    engine(tmp_path)
    key = vsr.store_asset(sample(tmp_path), 'Nguồn.mp4')
    calls = []
    monkeypatch.setattr(vsr, 'run_worker', lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError):
        vsr.remove({'asset': key, 'regions': REGIONS, 'subtitle_mode': 'import', 'subtitle_asset': uuid4().hex}, uuid4().hex, lambda *a: None, threading.Event())
    assert not calls and storage.asset(key)[0].is_file()
    assert not storage.read_json(storage.DATA/'vsr-index.json', [])


def test_embedded_text_subtitles_real(tmp_path):
    source = sample(tmp_path)
    sub = storage.asset(srt_asset(tmp_path))[0]
    muxed = tmp_path / 'embedded.mp4'
    media.command([media.binary(), '-y', '-v', 'error', '-i', str(source), '-i', str(sub), '-map', '0', '-map', '1:0', '-c', 'copy', '-c:s', 'mov_text', str(muxed)])
    folder = tmp_path / 'output'; folder.mkdir()
    output = vsr.original_subtitles({'subtitle_mode': 'embedded'}, muxed, media.probe(muxed), folder, threading.Event(), lambda *a: None)
    assert media.parse_srt(output.read_text(encoding='utf-8'))[0][0]['text'] == 'Xin chào'
    with pytest.raises(ValueError, match='không có track'):
        vsr.original_subtitles({'subtitle_mode': 'embedded'}, source, media.probe(source), folder, threading.Event(), lambda *a: None)


def test_worker_cancel_and_check_cli(tmp_path):
    engine(tmp_path)
    result = vsr.check(uuid4().hex, lambda *a: None, threading.Event())
    assert result['files'][0]['type'] == 'txt'
    event = threading.Event()
    timer = threading.Timer(.3, event.set); timer.start()
    try:
        with pytest.raises(InterruptedError):
            vsr.run_worker([sys.executable, '-c', 'import time;time.sleep(30)'], tmp_path, tmp_path/'cancel.log', event, lambda *a: None)
    finally:
        timer.cancel()


def test_download_srt_before_render_and_transfer(tmp_path, monkeypatch):
    source = sample(tmp_path)
    sub = storage.asset(srt_asset(tmp_path))[0]
    def fake(args, event, progress=None):
        assert '--write-subs' in args and '--write-auto-subs' in args
        assert args[args.index('--sub-langs')+1] == 'zh-Hans'
        target = Path(args[args.index('-o')+1].replace('%(ext)s', 'mp4'))
        shutil.copy2(source, target)
        shutil.copy2(sub, target.with_name('source.zh-Hans.srt'))
        return 'REUP_TITLE:Original'
    monkeypatch.setattr(downloads, 'process', fake)
    result = downloads.download({'urls':['https://example.com/video'], 'quality':'native', 'subtitles':True, 'auto_subtitles':True, 'subtitle_language':'zh-Hans'}, uuid4().hex, lambda *a: None, threading.Event())
    row = result['entries'][0]
    assert len(row['subtitles']) == 1
    assert storage.asset(row['subtitles'][0]['asset'])[0].is_file()
    assert {p.name for p in downloads.managed_files(row)} == {'video.mp4', 'source.zh-Hans.srt'}


def test_api_config_and_assets(tmp_path):
    with TestClient(make_app()) as client:
        client.get('/')
        assert client.get('/api/subtitle-removal').json()['runtime']['connected'] is False
        assert client.post('/api/subtitle-removal/config', json={'home':'','python':''}).status_code == 403
        token = client.get('/api/state').json()['csrf']
        assert client.post('/api/subtitle-removal/config', json={'home':'','python':''}, headers={'X-Reup-Token':token}).status_code == 200
        assert client.get('/static/removal-ui.js').status_code == 200


def test_prepare_srt_without_vsr_and_model_failure_retains_srt(tmp_path, monkeypatch):
    key = vsr.store_asset(sample(tmp_path), 'Nguồn.mp4')
    sub = srt_asset(tmp_path)
    payload = {'asset': key, 'regions': REGIONS, 'subtitle_mode': 'import', 'subtitle_asset': sub}
    assert not vsr.status()['connected']
    prepared = vsr.prepare_subtitle(payload, uuid4().hex, lambda *a: None, threading.Event())
    assert prepared['files'][0]['type'] == 'srt'
    assert storage.read_json(storage.DATA/'vsr-subtitles.json')[0]['subtitle_asset']
    engine(tmp_path)
    def fail(*a, **kw):raise RuntimeError('model missing')
    monkeypatch.setattr(vsr, 'run_worker', fail)
    with pytest.raises(RuntimeError, match='model missing'):
        vsr.remove(payload, uuid4().hex, lambda *a: None, threading.Event())
    rows = storage.read_json(storage.DATA/'vsr-subtitles.json')
    assert len(rows) == 2 and storage.asset(rows[0]['subtitle_asset'])[0].read_bytes() == storage.asset(sub)[0].read_bytes()
    assert not storage.read_json(storage.DATA/'vsr-index.json', [])


def test_bad_output_not_published_and_keeps_original(tmp_path, monkeypatch):
    engine(tmp_path)
    source = sample(tmp_path)
    key = vsr.store_asset(source, 'Nguồn.mp4')
    info = media.probe(source)
    stream = next(s for s in info['streams'] if s['codec_type']=='video')
    with pytest.raises(ValueError, match='thời lượng'):
        vsr.validate_video(source, stream, 4)
    with pytest.raises(ValueError, match='kích thước'):
        vsr.validate_video(source, {**stream, 'width':1920}, 1)
    def no_output(*a, **kw):pass
    monkeypatch.setattr(vsr, 'run_worker', no_output)
    with pytest.raises(ValueError, match='không tạo'):
        vsr.remove({'asset':key,'regions':REGIONS,'subtitle_mode':'none'}, uuid4().hex, lambda *a: None, threading.Event())
    assert storage.asset(key)[0].is_file()
    assert not storage.read_json(storage.DATA/'vsr-index.json', [])


def test_whisper_preparation_isolated_worker_contract(tmp_path, monkeypatch):
    key = vsr.store_asset(sample(tmp_path), 'Nguồn.mp4')
    def fake(args, cwd, log, event, progress, **kw):
        request = storage.read_json(Path(args[-1]))
        assert request['segments_only'] is True and request['allow_download'] is False
        assert Path(request['audio']).is_file()
        storage.atomic_json(Path(request['folder'])/'word-result.json', {'cues':[{'id':1,'start_ms':100,'end_ms':800,'source_text':'Lời gốc','text':'Lời gốc'}]})
    monkeypatch.setattr(vsr, 'run_worker', fake)
    result = vsr.prepare_subtitle({'asset':key,'subtitle_mode':'whisper','language':'vi'}, uuid4().hex, lambda *a: None, threading.Event())
    row = storage.read_json(storage.DATA/'vsr-subtitles.json')[0]
    assert media.parse_srt(storage.asset(row['subtitle_asset'])[0].read_text(encoding='utf-8'))[0][0]['text']=='Lời gốc'
    assert result['files'][0]['type']=='srt'
