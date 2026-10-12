"""The exact app assets must reload after an update, without deleting user data."""
import re

from fastapi.testclient import TestClient

from reup import VERSION, storage
from reup.server import make_app
from reup.web_build import web_page


def test_content_identity_changes_without_version_bump(tmp_path):
    (tmp_path / "index.html").write_text(
        '<meta content="__REUP_VERSION__"><script src="/static/app.js"></script>'
        '<link href="/static/editor.css"><meta content="__REUP_WEB_BUILD__">', encoding="utf-8")
    (tmp_path / "app.js").write_text("const version=1;", encoding="utf-8")
    (tmp_path / "editor.css").write_text("body{color:red}", encoding="utf-8")
    first, first_id = web_page(tmp_path)
    assert web_page(tmp_path) == (first, first_id)
    assert "__REUP_" not in first
    assert f'/static/app.js?v={first_id}' in first
    assert f'/static/editor.css?v={first_id}' in first
    (tmp_path / "editor.css").write_text("body{color:blue}", encoding="utf-8")
    assert web_page(tmp_path)[1] != first_id
    before_js = web_page(tmp_path)[1]
    (tmp_path / "app.js").write_text("const version=2;", encoding="utf-8")
    assert web_page(tmp_path)[1] != before_js


def test_ui_assets_identified_and_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    with TestClient(make_app()) as client:
        root = client.get("/")
        state = client.get("/api/state").json()
        assert root.headers["cache-control"] == "no-store"
        assert f'v{VERSION}' in root.text
        assert "__REUP_" not in root.text
        paths = re.findall(r'(?:href|src)="(/static/[^\"]+\.(?:css|js)\?v=[^\"]+)"', root.text)
        assert len(paths) == 23
        assert any(path.startswith('/static/backup-ui.js?v=') for path in paths)
        assert any('/tts-provider-ui.js?' in p for p in paths)
        assert any('/advanced-ai.js?' in p for p in paths)
        assert any('/llm-ui.js?' in p for p in paths)
        assert any(p.startswith('/static/compact.css?v=') for p in paths)
        for path in paths:
            assert path.endswith("?v=" + state["web_build"])
            result = client.get(path)
            assert result.status_code == 200
            assert result.headers["cache-control"] == "no-store"
        assert "mask-draw" in client.get("/static/editor-ui.js").text
        assert "dub-settings-scroll" in client.get("/static/editor.css").text
