"""Run optional installs in the appropriate interpreter, never importing into UI."""
import os
from pathlib import Path, PureWindowsPath
import sys

if __name__=='__main__':
    action=sys.argv[1]
    if action=='extract':
        import py7zr
        with py7zr.SevenZipFile(sys.argv[2]) as archive:
            for item in archive.list():
                name=item.filename.replace('\\','/')
                if name.startswith('/') or PureWindowsPath(name).is_absolute() or ':' in name or '..' in name.split('/') or getattr(item,'is_symlink',False):raise ValueError('Unsafe archive member')
            archive.extractall(path=sys.argv[3])
    elif action=='whisper':
        from faster_whisper import WhisperModel
        WhisperModel(sys.argv[2],device='cpu',compute_type='int8',download_root=sys.argv[3])
    elif action=='demucs':
        os.environ['TORCH_HOME']=sys.argv[2]
        from demucs.pretrained import get_model
        get_model('htdemucs')
    else:raise ValueError('Unknown library action')
    print('LIBRARY_READY')
