from pathlib import Path
import numpy as np
import pytest
sf = pytest.importorskip('soundfile', reason='This test runs in the separate VieNeu runtime, not the main backend venv')
from reup.engine_entry import trim_reference


def test_trim_edges_preserves_internal_pause(tmp_path):
    sr=48000
    speech=np.sin(np.arange(sr)*2*np.pi*440/sr).astype('float32')*.2
    wav=np.concatenate([np.zeros(sr),speech,np.zeros(sr),speech,np.zeros(sr)])
    source=tmp_path/'reference.wav';sf.write(source,wav,sr)
    output=tmp_path/'trim.wav'
    assert trim_reference(source,out_path=output)==str(output)
    actual,rate=sf.read(output)
    assert rate==sr and 2.9<len(actual)/sr<3.2
    assert abs(actual[len(actual)//2])<.001
    assert source.stat().st_size>output.stat().st_size


def test_trim_silent_missing(tmp_path):
    path=tmp_path/'absent.wav'
    assert trim_reference(path)==str(path)
    sf.write(path,np.zeros(48000),48000)
    output=Path(trim_reference(path,out_path=tmp_path/'silent.wav'))
    assert len(sf.read(output)[0])==48000
