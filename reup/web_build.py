"""Give each UI build a content identity, independent of browser/Qt caches."""
from hashlib import sha256
from pathlib import Path
import re

from . import VERSION


def web_page(folder: Path) -> tuple[str, str]:
    source = (folder / "index.html").read_text(encoding="utf-8")
    assets = sorted(set(re.findall(r'/static/([\w.-]+\.(?:js|css))', source)))
    digest = sha256((VERSION + source).encode("utf-8"))
    for name in assets:
        digest.update(name.encode("utf-8") + b"\0" + (folder / name).read_bytes())
    build = digest.hexdigest()[:16]
    source = re.sub(r'(/static/[\w.-]+\.(?:js|css))(?=["\'])',
                    lambda match: match[1] + "?v=" + build, source)
    return source.replace("__REUP_VERSION__", VERSION).replace("__REUP_WEB_BUILD__", build), build
