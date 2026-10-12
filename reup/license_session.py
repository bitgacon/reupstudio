"""Device-bound license refresh; Windows DPAPI storage, never raw activation keys."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import threading
import time
from . import storage

LOCK=threading.RLock()


def protect(value,decrypt=False):
    if os.name!='nt':raise ValueError('Lưu phiên bản quyền tự động cần Windows DPAPI.')
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(value)
    source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    if decrypt:
        fn=crypt.CryptUnprotectData;fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    else:
        fn=crypt.CryptProtectData;fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):raise ValueError('Không lưu/đọc được phiên bản quyền bảo vệ bằng Windows DPAPI.')
    try:return ctypes.string_at(output.data,output.size)
    finally:
        kernel=ctypes.WinDLL('kernel32');kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(ctypes.cast(output.data,ctypes.c_void_p))


def binding(config,machine):
    return hashlib.sha256(json.dumps([config.get('license_url'),config.get('public_key'),machine]).encode()).hexdigest()


def save(token,config,machine,expires):
    if not isinstance(token,str) or not 32<=len(token)<=256:raise ValueError('Phiên bản quyền không hợp lệ.')
    sealed=base64.b64encode(protect(token.encode())).decode()
    storage.atomic_json(storage.DATA/'license-session.json',{'sealed':sealed,'binding':binding(config,machine),'expires':expires})


def read(config,machine):
    row=storage.read_json(storage.DATA/'license-session.json',{})
    if row.get('binding')!=binding(config,machine) or not isinstance(row.get('expires'),(int,float)) or row['expires']<=time.time():return None
    try:
        token=protect(base64.b64decode(row['sealed'],validate=True),True).decode()
        if not 32<=len(token)<=256:return None
    except Exception:return None
    return {'token':token,'expires':row['expires']}


def clear():storage.atomic_json(storage.DATA/'license-session.json',{})


def remember(lease,envelope,config,machine):
    token=envelope.get('refresh_token')
    if token is None:
        clear();return False  # Compatibility with servers without refresh support.
    expires=lease.get('refresh_expires',0)
    if not isinstance(token,str) or hashlib.sha256(token.encode()).hexdigest()!=lease.get('refresh_sha256') or not time.time()<expires<=time.time()+30*86400+60:
        raise ValueError('Phản hồi phiên gia hạn bản quyền không hợp lệ.')
    save(token,config,machine,expires);return True


def start():
    """No network unless a configured issuer has a valid protected session."""
    from . import distribution
    stop=threading.Event()
    def worker():
        delay=60
        while not stop.is_set():
            try:
                config=distribution.policy();machine=distribution.machine_id()
                session=read(config,machine) if config.get('license_url') and config.get('public_key') else None
                status=distribution.license_status()
                if session and (not status['expires'] or status['expires']-time.time()<6*3600):
                    distribution.refresh_license();delay=60
                else:delay=60
            except Exception:delay=min(3600,max(300,delay*2))
            if stop.wait(delay):break
    thread=threading.Thread(target=worker,name='license-refresh',daemon=True);thread.start()
    return stop,thread
