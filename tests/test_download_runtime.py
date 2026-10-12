from pathlib import Path


def test_downloader_install_and_launcher_use_same_runtime_priority():
    root=Path(__file__).resolve().parents[1]
    for name in ['INSTALL_DOWNLOADS.bat','MO_REUP_VOICE_STUDIO.bat']:
        text=(root/name).read_text(encoding='utf-8')
        local=text.index('set "REUP_PYTHON=runtime\\python.exe"')
        source=text.index('set "REUP_PYTHON=..\\MoneyPrinterTurbo\\.venv\\Scripts\\python.exe"')
        release=text.index('set "REUP_PYTHON=..\\release\\MPT\\MoneyPrinterTurbo\\runtime\\python.exe"')
        assert local<source<release
    install=(root/'INSTALL_DOWNLOADS.bat').read_text(encoding='utf-8')
    assert 'where uv >nul 2>nul' in install
    assert "find_spec('pip')" in install
    assert '"%REUP_PYTHON%" -s -m yt_dlp --version' in install
    launcher=(root/'native'/'Launcher.cs').read_text(encoding='utf-8')
    assert launcher.index('"runtime", "pythonw.exe"') < launcher.index('".venv", "Scripts", "pythonw.exe"') < launcher.index('"release", "MPT"')
