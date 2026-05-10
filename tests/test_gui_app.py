from gui_app.app import (
    build_worker_command,
    build_worker_request,
    describe_skipped_target,
    describe_success_target,
    detect_worker_python,
    load_cookie_text_from_path,
    load_default_cookie_text,
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


def test_load_cookie_text_from_path_supports_config_yml(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
cookies:
  ttwid: abc
  msToken: xyz
""".strip(),
        encoding="utf-8",
    )

    cookies = parse_cookie_text(load_cookie_text_from_path(config_file))
    assert cookies == {"ttwid": "abc", "msToken": "xyz"}


def test_load_default_cookie_text_prefers_config_yml_over_cookie_json(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
cookies:
  ttwid: from-config
  msToken: from-config-token
""".strip(),
        encoding="utf-8",
    )
    cookie_dir = tmp_path / "config"
    cookie_dir.mkdir()
    (cookie_dir / "cookies.json").write_text(
        '{"ttwid": "from-json", "msToken": "from-json-token"}',
        encoding="utf-8",
    )

    content, source = load_default_cookie_text(project_root=tmp_path)

    assert parse_cookie_text(content) == {
        "ttwid": "from-config",
        "msToken": "from-config-token",
    }
    assert source == str(config_file)


def test_describe_success_target_handles_user_downloads():
    message = describe_success_target({"url_type": "user"})
    assert message == "Downloaded user content."


def test_describe_skipped_target_handles_user_downloads():
    message = describe_skipped_target({"url_type": "user"})
    assert message == "All matching user items were already available locally."


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


def test_build_worker_command_uses_module_for_source_runtime(tmp_path):
    request_file = tmp_path / "request.json"
    command = build_worker_command(
        python_executable="C:/Python/python.exe",
        request_file=request_file,
        frozen=False,
    )

    assert command == [
        "C:/Python/python.exe",
        "-m",
        "engine_api.worker",
        "--request-file",
        str(request_file),
    ]


def test_build_worker_command_reuses_frozen_executable(tmp_path):
    request_file = tmp_path / "request.json"
    command = build_worker_command(
        python_executable="",
        request_file=request_file,
        frozen=True,
        current_executable="C:/Apps/DouyinDownloader.exe",
    )

    assert command == [
        "C:\\Apps\\DouyinDownloader.exe",
        "--worker",
        "--request-file",
        str(request_file),
    ]


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
