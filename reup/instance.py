"""Local server discovery and a process-held lock, never kill port owners."""
from pathlib import Path
import requests


class InstanceLock:
    def __init__(self, folder: Path, name="server"):
        folder.mkdir(parents=True, exist_ok=True)
        self.file = (folder / f".{name}.lock").open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError(f"Một phiên Reup đang dùng kho {folder}. Không mở máy chủ thứ hai trên cổng khác.") from None

    def close(self):
        self.file.close()  # OS releases the lock, including on process exit/crash.


def identify_server(url, root, data, version, build):
    """Only attach to the same app, source, data and UI build. No redirects/proxies."""
    try:
        with requests.Session() as session:
            session.trust_env = False
            page = session.get(url + "/", timeout=3, allow_redirects=False)
            if page.status_code != 200 or 'name="reup-web-build"' not in page.text:
                raise ValueError("Cổng đang thuộc ứng dụng khác, không tự đóng tiến trình đó.")
            response = session.get(url + "/api/instance", timeout=3, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError("Máy chủ Reup cũ chưa hỗ trợ kết nối lại. Lưu dự án, dừng tác vụ, đóng cửa sổ máy chủ Python cũ (Ctrl+C), rồi mở bản mới; đóng Chrome thôi chưa dừng máy chủ.")
            info = response.json()
            if (info.get("app") != "reup-voice-studio" or
                    Path(info.get("root", "")).resolve() != root.resolve() or
                    Path(info.get("data", "")).resolve() != data.resolve()):
                raise ValueError("Cổng thuộc phiên khác thư mục mã hoặc kho dữ liệu; không kết nối nhầm hoặc tự tắt.")
            if info.get("version") != version or info.get("web_build") != build:
                raise ValueError("Máy chủ Reup đang chạy bản cũ. Lưu thay đổi, chờ tác vụ xong và đóng cửa sổ máy chủ Python cũ (Ctrl+C) trước khi mở bản cập nhật.")
            return info
    except requests.RequestException as exc:
        raise ValueError("Cổng bận nhưng không xác minh được máy chủ Reup; không tự tắt tiến trình.") from exc
