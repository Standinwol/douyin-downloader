import json

from engine_api.contracts import SingleItemDownloadRequest, SingleItemDownloadResponse
from engine_api.worker import _emit_stdout, main


def test_worker_emits_final_completed_event(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "job_id": "job-worker-success",
                "url": "https://www.douyin.com/video/1234567890123456789",
                "output_dir": str(tmp_path / "downloads"),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "engine_api.worker.run_single_item_download_sync",
        lambda request, emitter=None: SingleItemDownloadResponse(
            job_id=request.job_id,
            status="success",
            request_url=request.url,
            resolved_url=request.url,
            url_type="video",
            aweme_id="1234567890123456789",
            media_type="video",
            output_dir=request.output_dir,
            saved_files=[str(tmp_path / "downloads" / "demo.mp4")],
            file_names=["demo.mp4"],
            total=1,
            success_count=1,
        ),
    )

    exit_code = main(["--request-file", str(request_file)])
    lines = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 0
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "job.completed"
    assert payload["response"]["status"] == "success"
    assert payload["response"]["aweme_id"] == "1234567890123456789"


def test_worker_reports_invalid_request_payload(tmp_path, capsys):
    request_file = tmp_path / "bad-request.json"
    request_file.write_text("{not-valid-json", encoding="utf-8")

    exit_code = main(["--request-file", str(request_file)])
    lines = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 1
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "job.failed"
    assert payload["error_code"] == "invalid_request_payload"


def test_request_from_mapping_parses_boolean_strings():
    request = SingleItemDownloadRequest.from_mapping(
        {
            "url": "https://www.douyin.com/video/1234567890123456789",
            "output_dir": "./Downloaded",
            "cover": "false",
            "music": "0",
            "avatar": "no",
            "json": "off",
            "folderstyle": "true",
            "database": "1",
        }
    )

    assert request.cover is False
    assert request.music is False
    assert request.avatar is False
    assert request.json is False
    assert request.folderstyle is True
    assert request.database is True


def test_emit_stdout_escapes_non_ascii_payload(monkeypatch):
    written = []

    class _AsciiOnlyStdout:
        def write(self, text):
            assert isinstance(text, str)
            assert all(ord(char) < 128 for char in text)
            written.append(text)
            return len(text)

        def flush(self):
            return None

    monkeypatch.setattr("engine_api.worker.sys.stdout", _AsciiOnlyStdout())

    _emit_stdout(
        {
            "event": "job.completed",
            "response": {
                "saved_files": ["E:/下载/作者/作品.mp4"],
                "file_names": ["作品.mp4"],
            },
        }
    )

    payload = json.loads("".join(written))
    assert payload["response"]["saved_files"] == ["E:/下载/作者/作品.mp4"]
    assert payload["response"]["file_names"] == ["作品.mp4"]
