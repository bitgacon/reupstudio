"""Run the independent app, optionally in a native Qt WebEngine window."""
from __future__ import annotations

import argparse
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Open the default browser instead of a desktop window")
    parser.add_argument("--no-open", action="store_true", help="Serve only, for QA")
    parser.add_argument("--desktop-smoke", action="store_true", help="Load the Qt window then close automatically for QA")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    with socket.socket() as sock:
        occupied = sock.connect_ex(("127.0.0.1", args.port)) == 0
    from reup.server import make_app
    from reup import VERSION
    from reup.storage import DATA
    from reup.instance import InstanceLock, identify_server
    from reup.web_build import web_page
    import uvicorn
    url = f"http://127.0.0.1:{args.port}"
    app = server = thread = server_lock = None
    try:
        if occupied:
            identify_server(url, ROOT, DATA, VERSION, web_page(ROOT / "web")[1])
            print("Kết nối lại máy chủ Reup đang chạy; không tạo tiến trình xử lý thứ hai.", flush=True)
        else:
            server_lock = InstanceLock(DATA)
            app = make_app()
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f"Cổng {args.port}: {exc}") from None
    print(f"Reup Voice Studio {VERSION} — {url}\nNguồn: {ROOT}", flush=True)
    if args.browser or args.no_open:
        if not args.no_open:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        if server:
            try:
                server.run()
            finally:
                server_lock.close()
        return
    from PySide6.QtCore import QTimer, QUrl, QObject, Signal, Slot
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
    try:
        desktop_lock = InstanceLock(DATA, "desktop")
    except RuntimeError:
        raise SystemExit("Cửa sổ desktop Reup đã mở cho kho này. Kiểm tra thanh tác vụ Windows.") from None
    if server:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        if not server.started:
            raise SystemExit("Không mở được server ứng dụng.")
    qt = QApplication(sys.argv)
    qt.setApplicationName("Reup Voice Studio")
    from PySide6.QtGui import QIcon
    qt.setWindowIcon(QIcon(str(ROOT / "web" / "app.ico")))
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReupVoiceStudio.Desktop")
    class Window(QMainWindow):
        closing_after_job = False
        def closeEvent(self, event):
            if app is None:
                # Attached window does not own the browser server or its jobs.
                event.accept()
                return
            if app.state.queue.busy():
                if not self.closing_after_job:
                    choice = QMessageBox.question(self, "Đang có tác vụ", "Yêu cầu dừng và đóng sau bước hiện tại? Cửa sổ sẽ chờ tác vụ dừng an toàn; các cue đã lưu vẫn được giữ.")
                    if choice != QMessageBox.StandardButton.Yes:
                        event.ignore()
                        return
                    self.closing_after_job = True
                    for job in app.state.queue.all():
                        if job["status"] in {"queued", "running"}:
                            app.state.queue.cancel(job["id"])
                    self.setWindowTitle("Reup Voice Studio — Đang chờ dừng an toàn…")
                QTimer.singleShot(500, self.close)
                event.ignore()
                return
            app.state.queue.close()
            app.state.flow.engine.stop()
            server.should_exit = True
            event.accept()
    window = Window()
    if app:
        app.state.desktop_update = True
        app.state.update_exit = False
        update_timer = QTimer(window)
        update_timer.timeout.connect(lambda: window.close() if app.state.update_exit and not app.state.queue.busy() else None)
        update_timer.start(500)
    window.setWindowTitle("Reup Voice Studio " + VERSION)
    window.resize(1400, 900)
    window.setMinimumSize(960, 640)
    view = QWebEngineView(window)
    profile = QWebEngineProfile("ReupVoiceStudio", view)
    profile.setPersistentStoragePath(str(DATA / "web-profile"))
    profile.setCachePath(str(DATA / "web-cache"))
    # Keep localStorage and user drafts; only disable caching of app assets.
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    from reup.desktop_links import browser_page_class
    class Page(browser_page_class()):
        ui_ready = False

        def javaScriptConsoleMessage(self, level, message, line, source):
            if args.desktop_smoke and message.startswith("REUP_UI_READY="):
                self.ui_ready = message == f"REUP_UI_READY={VERSION}; pinned=true; mask=true"
                print(message, flush=True)
                QTimer.singleShot(500, window.close)
            else:
                super().javaScriptConsoleMessage(level, message, line, source)

    page = Page(profile, view)
    view.setPage(page)
    class FolderPicker(QObject):
        requested = Signal(object)

        def __init__(self):
            super().__init__()
            self.requested.connect(self.choose)

        @Slot(object)
        def choose(self, request):
            from PySide6.QtWidgets import QFileDialog
            try:
                request["path"] = QFileDialog.getExistingDirectory(window, "Chọn thư mục lưu dự án")
            finally:
                request["event"].set()

        def ask(self):
            request = {"event": threading.Event(), "path": ""}
            self.requested.emit(request)
            request["event"].wait(300)
            return request["path"]
    folder_picker = FolderPicker()
    if app is not None:
        app.state.pick_folder = folder_picker.ask
    def download(item):
        from PySide6.QtWidgets import QFileDialog
        target, _ = QFileDialog.getSaveFileName(window, "Lưu kết quả", item.downloadFileName())
        if target:
            item.setDownloadDirectory(str(Path(target).parent))
            item.setDownloadFileName(Path(target).name)
            item.accept()
        else:
            item.cancel()
    profile.downloadRequested.connect(download)
    def permission(origin, feature):
        allowed = origin.host() == "127.0.0.1" and feature == QWebEnginePage.Feature.MediaAudioCapture
        if allowed:
            allowed = QMessageBox.question(window, "Micro", "Cho phép thu mẫu giọng từ micro?") == QMessageBox.StandardButton.Yes
        page.setFeaturePermission(origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                                  if allowed else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
    page.featurePermissionRequested.connect(permission)
    if args.desktop_smoke:
        def loaded(ok):
            print("QT_WEBENGINE_LOAD=" + str(ok), flush=True)
        view.loadFinished.connect(loaded)
        QTimer.singleShot(30000, window.close)
    view.setUrl(QUrl(url + ("?smoke=1" if args.desktop_smoke else "")))
    window.setCentralWidget(view)
    window.show()
    result = qt.exec()
    if server:
        server.should_exit = True
        thread.join(timeout=15)
        server_lock.close()
    desktop_lock.close()
    if args.desktop_smoke and not page.ui_ready:
        print("REUP_UI_READY=FAILED (giao diện chưa khởi tạo xong)", flush=True)
        return 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
