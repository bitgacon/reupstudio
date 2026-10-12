import sys
from pathlib import Path
import threading
import pytest
from reup import subtitle_removal as vsr

def bundle(tmp_path):
    root=tmp_path/'VSR';home=root/'resources';home.mkdir(parents=True)
    python=root/'Python/python.exe';python.parent.mkdir()
    hook=python.parent/'Lib/site-packages/sitecustomize.py';hook.parent.mkdir(parents=True);hook.write_text('# QPT packaged first run')
    (root/'opt/packages').mkdir(parents=True);(root/'opt/requirements_dev.txt').write_text('numpy==2.2.5')
    return root,home,python

def test_detects_only_matched_qpt_runtime(tmp_path):
    root,home,python=bundle(tmp_path)
    assert vsr.qpt_bundle(home,python)==root
    assert vsr.qpt_bundle(home,Path(sys.executable)) is None
    assert vsr.qpt_bundle(tmp_path/'other',python) is None

def test_qpt_bootstrap_is_offline_and_separate(tmp_path,monkeypatch):
    root,home,python=bundle(tmp_path);folder=tmp_path/'job';folder.mkdir();calls=[]
    def fake(args,cwd,log,*a,**k):
        calls.append((args,cwd));log.write_text('VSR_DEPS_MISSING' if args[1]=='-c' else 'installed')
    monkeypatch.setattr(vsr,'run_worker',fake)
    vsr.prepare_runtime(home,python,folder,threading.Event(),lambda *a:None)
    assert len(calls)==2
    args,cwd=calls[1];assert args[0]==str(python) and cwd==home
    assert '--no-index' in args and '--no-deps' in args and '--no-build-isolation' in args
    assert str(root/'opt/packages') in args and str(root/'opt/requirements_dev.txt') in args
    assert (root/'opt/requirements_dev.txt').is_file()

def test_ready_qpt_does_not_reinstall(tmp_path,monkeypatch):
    root,home,python=bundle(tmp_path);folder=tmp_path/'job';folder.mkdir();calls=[]
    def fake(args,cwd,log,*a,**k):calls.append(args);log.write_text('VSR_DEPS_OK')
    monkeypatch.setattr(vsr,'run_worker',fake)
    vsr.prepare_runtime(home,python,folder,threading.Event(),lambda *a:None)
    assert len(calls)==1 and '-m' not in calls[0]

def test_missing_offline_package_folder_is_actionable(tmp_path):
    root,home,python=bundle(tmp_path)
    (root/'opt/packages').rmdir()
    with pytest.raises(ValueError,match='opt/packages'):vsr.prepare_runtime(home,python,tmp_path,threading.Event(),lambda *a:None)

def test_qpt_env_reaches_worker_without_parent_override(tmp_path,monkeypatch):
    root,home,python=bundle(tmp_path);captured={}
    class Process:
        returncode=0
        def poll(self):return 0
    def launch(args,**kwargs):captured.update(kwargs);return Process()
    monkeypatch.setattr(vsr.subprocess,'Popen',launch)
    monkeypatch.setattr(vsr.media,'stop_owned_process',lambda p:None)
    monkeypatch.setenv('QPT_MODE','Debug');monkeypatch.setenv('PYTHONPATH','wrong')
    vsr.run_worker([str(python),'--check'],home,tmp_path/'log.txt',threading.Event(),lambda *a:None)
    assert captured['env']['QPT_MODE']=='Running' and 'PYTHONPATH' not in captured['env']
