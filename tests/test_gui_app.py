from pathlib import Path

from gui_app.app import (
    build_worker_request,
    detect_worker_python,
    normalize_python_executable,
    parse_cookie_text,
)


def test_parse_cookie_text_supports_json_dict():
    cookies = parse_cookie_text('{"ttwid": "abc", "msToken": "xyz"}')
    assert cookies == {"ttwid": "abc", "msToken": "xyz"}


def test_parse_cookie_text_supports_cookie_header():
    cookies = parse_cookie_text("ttwid=abc; msToken=xyz; invalid item")
    assert cookies == {"ttwid": "abc", "msToken": "xyz"}


def test_parse_cookie_text_supports_list_payload():
    cookies = parse_cookie_text('[{"name": "ttwid", "value": "abc"}, {"name": "msToken", "value": "xyz"}]')
    assert cookies == {"ttwid": "abc", "msToken": "xyz"}


def test_normalize_python_executable_prefers_python_exe(tmp_path):
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    python_exe = scripts_dir / "python.exe"
    python_exe.write_text("", encoding="utf-8")
    pythonw_exe = scripts_dir / "pythonw.exe"
    pythonw_exe.write_text("", encoding="utf-8")

    assert normalize_python_executable(str(pythonw_exe)) == str(python_exe)


def test_detect_worker_python_prefers_local_venv(tmp_path):
    project_root = tmp_path
    local_python = project_root / ".venv" / "Scripts" / "python.exe"
    local_python.parent.mkdir(parents=True)
    local_python.write_text("", encoding="utf-8")

    detected = detect_worker_python(project_root=project_root, current_executable="C:/Python/python.exe")
    assert detected == str(local_python)


def test_build_worker_request_maps_gui_flags():
    payload = build_worker_request(
        url="https://www.douyin.com/video/123",
        output_dir="./Downloaded",
        cookies={"ttwid": "abc"},
        proxy="http://127.0.0.1:7890",
        cover=False,
        music=True,
        avatar=False,
        json_metadata=True,
        database=False,
    )

    assert payload["url"] == "https://www.douyin.com/video/123"
    assert payload["output_dir"] == "./Downloaded"
    assert payload["cookies"] == {"ttwid": "abc"}
    assert payload["proxy"] == "http://127.0.0.1:7890"
    assert payload["cover"] is False
    assert payload["music"] is True
    assert payload["avatar"] is False
    assert payload["json"] is True
    assert payload["database"] is False
