"""Signed licensing leases and update metadata. Unconfigured private builds stay usable."""
import base64
import hashlib
import json
import platform
import secrets
import time
from urllib.parse import urlsplit, urljoin

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from . import VERSION, storage


def policy():
    return storage.read_json(storage.ROOT / "release-policy.json", {})


def machine_id():
    identity = platform.node()
    if platform.system() == "Windows":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                           winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            identity = winreg.QueryValueEx(key, "MachineGuid")[0]
    return hashlib.sha256(("reup:" + identity).encode()).hexdigest()


def verified(envelope):
    raw = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    Ed25519PublicKey.from_public_bytes(base64.b64decode(policy()["public_key"], validate=True)).verify(signature, raw)
    return json.loads(raw)


def https(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("Nguồn bản quyền/cập nhật phải là HTTPS, không chứa mật khẩu.")
    return url


def get_https(session, url, **kwargs):
    """Dropbox redirects are expected; validate every hop, never downgrade TLS."""
    for _ in range(6):
        response = session.get(https(url), allow_redirects=False, **kwargs)
        if response.status_code not in (301, 302, 303, 307, 308):
            response.raise_for_status()
            return response
        next_url = urljoin(url, response.headers.get('Location', ''))
        response.close()
        if next_url == url:
            raise ValueError('Nguồn cập nhật chuyển hướng không hợp lệ.')
        url = https(next_url)
    raise ValueError('Nguồn cập nhật chuyển hướng quá nhiều lần.')


def license_status():
    config = policy()
    required = bool(config.get("license_required"))
    result = {"required": required, "configured": bool(config.get("license_url") and config.get("public_key")),
              "active": not required, "machine": machine_id(), "expires": None}
    if not result["configured"]:
        return {**result, "message": "Bản cá nhân: chưa kết nối máy chủ bản quyền." if not required else "Chưa cấu hình máy chủ bản quyền."}
    try:
        lease = verified(storage.read_json(storage.DATA / "license.json", {}))
        if lease["product"] != "reup-voice-studio" or lease["machine"] != result["machine"] or lease["expires"] <= time.time():
            raise ValueError("Lease expired")
        return {**result, "active": True, "expires": lease["expires"], "message": "Key đang có hiệu lực."}
    except Exception:
        return {**result, "message": "Chưa kích hoạt hoặc key hết hạn. Nhập key để xác thực lại."}


def activate(key):
    from .license_session import LOCK
    with LOCK:return _activate(key)


def _activate(key):
    config = policy()
    if not config.get("license_url") or not config.get("public_key"):
        raise ValueError("Chưa triển khai máy chủ bản quyền; xem hướng dẫn quản trị.")
    if not isinstance(key, str) or not 8 <= len(key) <= 256:
        raise ValueError("Key không hợp lệ.")
    nonce = secrets.token_hex(24)
    session = requests.Session()
    session.trust_env = False
    response = session.post(https(config["license_url"]).rstrip("/") + "/v1/activate",
                            json={"key": key.strip(), "machine": machine_id(), "nonce": nonce, "refresh":True}, timeout=(10, 20), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("Máy chủ từ chối key hoặc chưa kết nối được (HTTP %s)." % response.status_code)
    envelope = response.json()
    lease = verified(envelope)
    if (lease.get("nonce") != nonce or lease.get("machine") != machine_id() or lease.get("product") != "reup-voice-studio"
            or not time.time() < lease.get("expires", 0) <= time.time() + 86460):
        raise ValueError("Phản hồi bản quyền không hợp lệ.")
    from . import license_session
    license_session.remember(lease,envelope,config,machine_id())
    # Neither the activation key nor the plaintext refresh token is saved here.
    storage.atomic_json(storage.DATA / "license.json", {k:envelope[k] for k in ('payload','signature')})
    return license_status()


def refresh_license():
    from . import license_session
    with license_session.LOCK:
        config=policy();machine=machine_id();saved=license_session.read(config,machine)
        if not saved:raise ValueError('Chưa có phiên gia hạn; nhập key để kích hoạt lại một lần.')
        nonce=secrets.token_hex(24)
        try:
            with requests.Session() as session:
                session.trust_env=False
                response=session.post(https(config['license_url']).rstrip('/')+'/v1/refresh',
                    json={'token':saved['token'],'machine':machine,'nonce':nonce},timeout=(10,20),allow_redirects=False)
        except requests.RequestException:
            raise ValueError('Chưa kết nối được máy chủ gia hạn; lease còn hạn vẫn sử dụng được.') from None
        if response.status_code==403:
            license_session.clear();storage.atomic_json(storage.DATA/'license.json',{})
            raise ValueError('Phiên bản quyền đã bị thu hồi/hết hạn; nhập key hợp lệ để kích hoạt lại.')
        if response.status_code!=200:raise ValueError('Máy chủ gia hạn chưa sẵn sàng (HTTP %s); lease hiện tại được giữ.'%response.status_code)
        envelope=response.json();lease=verified(envelope);now=time.time()
        if lease.get('nonce')!=nonce or lease.get('machine')!=machine or lease.get('product')!='reup-voice-studio' or not now<lease.get('expires',0)<=now+86460 or lease.get('refresh_sha256')!=hashlib.sha256(saved['token'].encode()).hexdigest() or not now<lease.get('refresh_expires',0)<=now+30*86400+60:
            raise ValueError('Phản hồi gia hạn bản quyền không hợp lệ; lease cũ được giữ.')
        license_session.save(saved['token'],config,machine,lease['refresh_expires'])
        storage.atomic_json(storage.DATA/'license.json',{k:envelope[k] for k in ('payload','signature')})
        return license_status()


def check_update():
    url = policy().get("update_url", "")
    if not url:
        return {"configured": False, "available": False, "message": "Chưa thiết lập nguồn phát hành. Khi có nguồn, app luôn tự kiểm tra và tải bản mới."}
    session = requests.Session()
    session.trust_env = False
    response = get_https(session, url, timeout=(10, 20))
    response.raise_for_status()
    if len(response.content) > 65536:
        raise ValueError("Manifest cập nhật quá lớn.")
    manifest = verified(response.json())
    version = manifest["version"]
    import re
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or manifest.get("product") != "reup-voice-studio":
        raise ValueError("Phiên bản cập nhật không hợp lệ.")
    if not re.fullmatch(r"[a-f0-9]{64}", manifest.get("sha256", "")):
        raise ValueError("Thiếu hash bộ cài.")
    https(manifest["url"])
    available = tuple(map(int, version.split("."))) > tuple(map(int, VERSION.split(".")))
    return {"configured": True, "available": available, "version": version,
            "message": "Có bản mới " + version if available else "Đang dùng phiên bản mới nhất.", "manifest": manifest}


def download_update():
    result = check_update()
    if not result["available"]:
        raise ValueError(result["message"])
    manifest = result["manifest"]
    from pathlib import Path
    ready = storage.read_json(storage.DATA / 'ready-update.json', {})
    cached = Path(ready.get('path', '')).resolve()
    if ready.get('version') == manifest['version'] and ready.get('sha256') == manifest['sha256'] and cached.is_file():
        with cached.open('rb') as stream:
            cached_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        if cached_hash == manifest['sha256']:
            from .workflows import artifact
            return {'file':artifact(cached), 'message':'Bộ cài đã tải và xác minh, sẵn sàng cập nhật.'}
    path = storage.output_folder("documents", secrets.token_hex(16)) / ("ReupVoiceStudio-" + manifest["version"] + "-Setup.exe")
    digest = hashlib.sha256()
    try:
        session = requests.Session()
        session.trust_env = False
        with get_https(session, manifest["url"], stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            size = 0
            with path.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > 8 * 1024**3:
                        raise ValueError("Bộ cài vượt giới hạn 8 GB.")
                    digest.update(chunk)
                    stream.write(chunk)
        if digest.hexdigest() != manifest["sha256"]:
            raise ValueError("Hash bộ cài không khớp; file tải đã loại bỏ.")
        storage.atomic_json(storage.DATA / 'ready-update.json', {'path':str(path), 'sha256':manifest['sha256'], 'version':manifest['version']})
        from .workflows import artifact
        return {"file": artifact(path), "message": "Đã kiểm tra chữ ký manifest và SHA256. Đóng ứng dụng trước khi chạy bộ cài."}
    except Exception:
        path.unlink(missing_ok=True)
        raise


def launch_update():
    """Only launch the previously verified installer, never a client-supplied path."""
    import os
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    if os.name != 'nt' or not (storage.ROOT / 'installed.flag').is_file():
        raise ValueError('Tự cài cập nhật chỉ dùng trong bản đã cài trên Windows.')
    ready = storage.read_json(storage.DATA / 'ready-update.json', {})
    path = Path(ready.get('path', '')).resolve()
    if not path.is_file() or path.name != f"ReupVoiceStudio-{ready.get('version')}-Setup.exe":
        raise ValueError('Chưa có bộ cài đã xác minh.')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != ready.get('sha256'):
            raise ValueError('Hash bộ cài không khớp; không cập nhật.')
    folder = Path(tempfile.mkdtemp(prefix='Reup-update-'))
    helper = folder / 'ReupUpdater.exe'
    shutil.copy2(storage.ROOT / 'ReupVoiceStudio.exe', helper)
    parent_pid = str(int(os.environ.get('REUP_LAUNCHER_PID', '0')))
    subprocess.Popen([str(helper), '--apply-update', str(path), ready['sha256'], str(os.getpid()), str(storage.ROOT), parent_pid],
                     creationflags=subprocess.CREATE_NO_WINDOW)
    return {'ok':True, 'message':'Đang đóng app an toàn để cài cập nhật; app sẽ mở lại khi xong.'}
