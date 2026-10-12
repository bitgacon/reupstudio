import json
import os
import pytest
from reup import storage

def test_durable_write_keeps_previous_valid_backup(tmp_path,monkeypatch):
    calls=[];original=os.fsync
    monkeypatch.setattr(os,'fsync',lambda fd:(calls.append(fd),original(fd)))
    p=tmp_path/'settings.json';storage.atomic_json(p,{'a':1});storage.atomic_json(p,{'a':2})
    assert storage.read_json(p)=={'a':2}
    assert json.loads(p.with_name(p.name+'.bak').read_text())=={'a':1}
    assert len(calls)==3

def test_zeroed_primary_recovers_and_preserves_evidence(tmp_path):
    p=tmp_path/'settings.json';storage.atomic_json(p,{'a':1});storage.atomic_json(p,{'a':2})
    p.write_bytes(b'\0'*579)
    assert storage.read_json(p)=={'a':1}
    assert storage.read_json(p)=={'a':1}
    copies=list(tmp_path.glob('settings.json.corrupt-*'))
    assert len(copies)==1 and copies[0].read_bytes()==b'\0'*579

def test_corrupt_without_backup_is_not_silently_reset(tmp_path):
    p=tmp_path/'project.json';p.write_bytes(b'\0'*50)
    with pytest.raises(ValueError,match='chưa có bản sao hợp lệ'):storage.read_json(p,{})
    assert p.read_bytes()==b'\0'*50

def test_broken_backup_and_primary_are_kept(tmp_path):
    p=tmp_path/'project.json';p.write_bytes(b'{');p.with_name(p.name+'.bak').write_bytes(b'broken')
    with pytest.raises(ValueError):storage.read_json(p)
    assert p.read_bytes()==b'{' and p.with_name(p.name+'.bak').read_bytes()==b'broken'

def test_missing_primary_restores_backup(tmp_path):
    p=tmp_path/'project.json';p.with_name(p.name+'.bak').write_text('{"a":1}')
    assert storage.read_json(p)=={'a':1} and p.exists()

def test_failed_replace_leaves_previous_file(tmp_path,monkeypatch):
    p=tmp_path/'project.json';storage.atomic_json(p,{'a':1});replace=os.replace
    def fail(src,dst):
        if dst==p:raise OSError('simulated interruption')
        replace(src,dst)
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):storage.atomic_json(p,{'a':2})
    assert storage.read_json(p)=={'a':1} and not list(tmp_path.glob('*.tmp'))
