"""Isolated CPU entry. Avoid cold librosa/Numba JIT just to trim clone references."""
import faulthandler
import os
from pathlib import Path
import tempfile

import numpy as np
import soundfile as sf


def trim_reference(ref_audio, *, top_db=30, out_path=None):
    source=Path(ref_audio)
    if not source.is_file():
        return str(source)
    wav,sr=sf.read(str(source),dtype='float32',always_2d=False)
    if wav.ndim>1:
        wav=wav.mean(axis=1)
    if not len(wav):
        return str(source)
    # Relative frame power, like librosa.effects.trim; preserve pauses inside the clip.
    padded=np.pad(wav.astype(np.float64),1024)
    cumulative=np.concatenate(([0.],np.cumsum(padded*padded)))
    starts=np.arange(0,len(padded)-2048+1,512)
    power=(cumulative[starts+2048]-cumulative[starts])/2048
    active=np.flatnonzero(power>max(float(power.max()),1e-20)*10**(-float(top_db)/10))
    if active.size:
        start=max(int(starts[active[0]])-1024,0)
        end=min(int(starts[active[-1]])+1024,len(wav))
        wav=wav[start:end]
    if out_path is None:
        fd,out_path=tempfile.mkstemp(prefix='reup-clone-',suffix='.wav')
        os.close(fd)
    sf.write(str(out_path),wav,sr)
    return str(out_path)


if __name__=='__main__':
    if os.environ.get('REUP_ENGINE_TRACE')=='1':
        faulthandler.dump_traceback_later(60,repeat=True)
    from vieneu.v3turbo import V3TurboVieNeuTTS
    V3TurboVieNeuTTS._preclean_reference_audio=staticmethod(trim_reference)
    from apps.openai_speech import main
    main()
