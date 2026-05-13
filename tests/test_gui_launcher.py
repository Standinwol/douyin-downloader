import sys

from gui_app import launcher


def test_configure_portable_runtime_sets_playwright_browser_path(monkeypatch, tmp_path):
    browser_dir = tmp_path / "ms-playwright"
    browser_dir.mkdir()

    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(launcher, "_portable_base_dir", lambda: tmp_path)

    launcher._configure_portable_runtime()

    assert launcher.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_dir)


def test_configure_portable_runtime_preserves_existing_browser_path(monkeypatch, tmp_path):
    browser_dir = tmp_path / "ms-playwright"
    browser_dir.mkdir()

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "C:/custom/ms-playwright")
    monkeypatch.setattr(launcher, "_portable_base_dir", lambda: tmp_path)

    launcher._configure_portable_runtime()

    assert launcher.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "C:/custom/ms-playwright"


def test_portable_base_dir_uses_executable_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "DouyinDownloader.exe"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert launcher._portable_base_dir() == tmp_path
