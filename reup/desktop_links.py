"""Only ordinary external web links may leave the embedded app."""
from urllib.parse import urlsplit


def external_url(value):
    try:
        u=urlsplit(value)
        return u.scheme in {'https','http'} and bool(u.hostname) and u.hostname not in {'127.0.0.1','localhost','::1'} and not u.username and not u.password
    except ValueError:
        return False


def browser_page_class(opener=None):
    """Lazy Qt import; shared by desktop launcher and offscreen acceptance."""
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QDesktopServices
    class BrowserPage(QWebEnginePage):
        popup=False
        def acceptNavigationRequest(self,target,navigation_type,is_main_frame):
            if external_url(target.toString()):
                (opener or QDesktopServices.openUrl)(target)
                if self.popup:QTimer.singleShot(0,self.deleteLater)
                return False
            return super().acceptNavigationRequest(target,navigation_type,is_main_frame)
        def createWindow(self,window_type):
            child=BrowserPage(self.profile(),self);child.popup=True
            return child
    return BrowserPage
