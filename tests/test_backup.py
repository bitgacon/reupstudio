import hashlib
import json
from pathlib import Path
from uuid import uuid4
import zipfile
import pytest
from fastapi.testclient import TestClient
from reup import backup, storage
from reup.server import make_app
from reup.jobs import JobQueue


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path / 'data')
    storage.DATA.mkdir()


def seed():
    p = storage.new_project('Dự án thử')
    key = uuid4().hex; root = storage.project_path(p['id'])
    (root / 'assets').mkdir(); (root / 'assets' / (key + '.mp4')).write_bytes(b'project-source')
    p.update(video=key, local_assets={key: {'file': key + '.mp4', 'name': 'nguồn.mp4'}},
             cues=[{'id': 1, 'start_ms': 0, 'end_ms': 1500, 'text': 'Xin chào', 'audio': 'cue.wav', 'status': 'complete'}], translation_consent=True)
    (root / 'cues').mkdir(); (root / 'cues' / 'cue.wav').write_bytes(b'cue-audio')
    storage.save_project(p)
    storage.save_settings({'translation_key': 'secret-key', 'translation_url': 'https://api.example.com/v1', 'translation_model': 'model'})
    storage.atomic_json(storage.DATA / 'tts-provider-settings.json', {'device': 'cpu', 'elevenlabs_key': 'secret-eleven'})
    return p


def archive_path(result):
    return storage.DATA / result['url'][7:]


def rewrite(source, mutate=None, extra=None):
    target = source.with_name(uuid4().hex + '.rvbackup')
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(target, 'w') as out:
        value = json.loads(z.read('manifest.json'))
        if mutate: mutate(value)
        out.writestr('manifest.json', json.dumps(value))
        for name in z.namelist():
            if name != 'manifest.json': out.writestr(name, z.read(name))
        if extra: out.writestr(*extra)
    return target


def test_portable_local_only_source_audio_additive_and_secrets():
    p = seed(); source = archive_path(backup.create([p['id']]))
    with zipfile.ZipFile(source) as z:
        content = z.read('manifest.json')
        assert b'secret-key' not in content and b'secret-eleven' not in content
    assert backup.inspect(source)['projects'][0]['cues'] == 1
    for _ in range(2):
        restored = backup.restore(source, settings=True)['projects'][0]
        result = storage.project(restored['id'])
        assert restored['id'] != p['id'] and not result['translation_consent']
        assert result['video'] != p['video']
        assert storage.project_asset(result, result['video'])[0].read_bytes() == b'project-source'
        assert (storage.project_path(result['id']) / 'cues' / 'cue.wav').read_bytes() == b'cue-audio'
    assert len(storage.list_projects()) == 3
    assert storage.settings()['translation_key'] == 'secret-key'
    assert storage.read_json(storage.DATA / 'tts-provider-settings.json')['elevenlabs_key'] == 'secret-eleven'
    assert list((storage.DATA / 'backups').glob('settings-before-*'))


def test_settings_only_keys_opt_in_and_machine_paths_stay():
    seed(); source = archive_path(backup.create([], include_keys=True))
    storage.save_settings({'translation_key': 'current-key'})
    backup.restore(source, projects=False, settings=True)
    assert storage.settings()['translation_key'] == 'current-key'
    backup.restore(source, projects=False, settings=True, keys=True)
    assert storage.settings()['translation_key'] == 'secret-key'
    assert not backup.inspect(source)['projects']


def test_editor_assets_remap():
    p = seed(); from reup.timeline import Timeline
    timeline = Timeline(assets=[p['video']]).model_dump()
    storage.atomic_json(storage.project_path(p['id']) / 'editor-timeline.json', timeline)
    result = backup.restore(archive_path(backup.create([p['id']])))['projects'][0]
    new = storage.project(result['id'])
    tl = storage.read_json(storage.project_path(new['id']) / 'editor-timeline.json')
    assert tl['assets'] == [new['video']]
    Timeline.model_validate(tl)


def test_reference_speech_and_stems_are_portable_cloud_requires_reconsent():
    p = seed(); key = uuid4().hex; folder = storage.DATA / 'uploads' / key
    folder.mkdir(parents=True); (folder / 'source.wav').write_bytes(b'reference-speech')
    storage.atomic_json(folder / 'asset.json', {'id': key, 'file': 'source.wav', 'name': 'reference.wav'})
    p['tts'] = {'provider': 'chatterbox', 'language': 'en', 'voice': 'default', 'reference_asset': key, 'reference_consent': True}
    p['cues'][0]['tts'] = {'provider': 'elevenlabs', 'language': 'en', 'voice': 'default', 'cloud_consent': True}
    root = storage.project_path(p['id']); (root / 'stems').mkdir()
    (root / 'stems' / 'no_vocals.wav').write_bytes(b'music-stem')
    storage.save_project(p)
    result = backup.restore(archive_path(backup.create([p['id']])))['projects'][0]
    new = storage.project(result['id'])
    assert not new['cues'][0]['tts']['cloud_consent']
    assert new['tts']['reference_asset'] != key
    assert storage.asset(new['tts']['reference_asset'])[0].read_bytes() == b'reference-speech'
    assert (storage.project_path(new['id']) / 'stems' / 'no_vocals.wav').read_bytes() == b'music-stem'


def test_profiles_append_with_no_secret_and_keep_current_provider():
    seed(); key = uuid4().hex
    storage.atomic_json(storage.DATA / 'llm-profiles.json', {'active': key, 'profiles': [{'id': key, 'name': 'LLM sample', 'provider': 'custom', 'url': 'https://api.example.com/v1', 'model': 'model', 'key': 'profile-secret', 'batch_size': 10, 'pause_seconds': 2}]})
    source = archive_path(backup.create([]))
    storage.save_settings({'translation_url': 'https://current.example.com/v1', 'translation_model': 'current', 'translation_key': 'current-secret'})
    backup.restore(source, projects=False, settings=True)
    config = storage.settings(); rows = storage.read_json(storage.DATA / 'llm-profiles.json')['profiles']
    assert config['translation_url'] == 'https://current.example.com/v1' and config['translation_key'] == 'current-secret'
    assert len(rows) == 2 and rows[0]['key'] == 'profile-secret' and rows[1]['key'] == '' and rows[1]['id'] != key


@pytest.mark.parametrize('bad', ['hash', 'traversal', 'duplicate', 'unexpected', 'settings', 'missing'])
def test_invalid_archive_never_creates_project_or_changes_settings(bad):
    p = seed(); source = archive_path(backup.create([p['id']]))
    if bad == 'hash':
        source = rewrite(source, lambda v: next(iter(v['files'].values())).update(sha256='0' * 64))
    elif bad == 'traversal': source = rewrite(source, extra=('../evil.txt', 'evil'))
    elif bad == 'duplicate': source = rewrite(source, extra=('MANIFEST.JSON', '{}'))
    elif bad == 'unexpected': source = rewrite(source, extra=('run.exe', 'evil'))
    elif bad == 'settings': source = rewrite(source, lambda v: v['settings'].update({'settings.json': {'output_root': 'C:\\wrong'}}))
    else: source = rewrite(source, lambda v: v['projects'][0]['assets'].clear())
    index = storage.read_json(storage.DATA / 'project-index.json')
    settings = storage.settings()
    with pytest.raises(ValueError): backup.restore(source, settings=True, keys=True)
    assert storage.read_json(storage.DATA / 'project-index.json') == index
    assert storage.settings() == settings and len(storage.list_projects()) == 1
    assert not list((storage.DATA / '.restore').glob('*'))


def test_missing_media_leaves_no_archive():
    p = seed(); storage.project_asset(p, p['video'])[0].unlink()
    with pytest.raises(ValueError): backup.create([p['id']])
    assert not list(storage.DATA.glob('outputs/Backups/*'))


def test_restore_failure_rolls_back_created_projects(monkeypatch):
    p = seed(); source = archive_path(backup.create([p['id']]))
    original = storage.atomic_json
    def fail(path, value):
        if Path(path).name == 'settings.json': raise OSError('disk full')
        return original(path, value)
    monkeypatch.setattr(storage, 'atomic_json', fail)
    with pytest.raises(OSError): backup.restore(source, settings=True)
    assert len(storage.list_projects()) == 1
    assert not list((storage.DATA / 'projects').glob('*restored*'))
    assert storage.settings()['translation_key'] == 'secret-key'


def test_server_csrf_confirmation_upload_and_busy():
    p = seed(); app = make_app()
    with TestClient(app) as client:
        client.get('/')
        csrf = client.get('/api/state').json()['csrf']; headers = {'X-Reup-Token': csrf}
        body = {'project_ids': [p['id']]}
        assert client.post('/api/backups/create', json=body).status_code == 403
        created = client.post('/api/backups/create', json=body, headers=headers)
        assert created.status_code == 200
        content = client.get(created.json()['url']); assert content.status_code == 200
        asset = client.post('/api/upload', files={'file': ('backup.rvbackup', content.content)}, headers=headers).json()['id']
        assert client.post('/api/backups/inspect', json={'asset_id': asset}, headers=headers).json()['projects']
        assert client.post('/api/backups/restore', json={'asset_id': asset}, headers=headers).status_code == 400
        app.state.queue.rows['fake'] = {'status': 'running'}
        assert client.post('/api/backups/create', json=body, headers=headers).status_code == 400
        app.state.queue.rows.clear()
        response = client.post('/api/backups/restore', json={'asset_id': asset, 'confirmed': True}, headers=headers)
        assert response.status_code == 200 and len(storage.list_projects()) == 2


def test_idle_gate_rejects_jobs_and_restores_gate_even_after_error():
    queue = JobQueue(lambda *a: {})
    try:
        with pytest.raises(ValueError, match='test error'):
            with backup.idle(queue):
                with pytest.raises(ValueError, match='sao lưu'): queue.submit('tts', {})
                with pytest.raises(ValueError):
                    with backup.idle(queue): pass
                assert queue.all() == []
                raise ValueError('test error')
        assert not queue.maintenance and queue.accepting
        assert queue.submit('tts', {})['id']
    finally: queue.close()
