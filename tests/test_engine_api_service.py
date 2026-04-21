from core.downloader_base import DownloadResult
from engine_api.contracts import SingleItemDownloadRequest
from engine_api.service import run_single_item_download_sync


def test_single_item_service_resolves_short_link_and_returns_artifacts(
    monkeypatch, tmp_path
):
    events = []

    class _FakeAPIClient:
        def __init__(self, cookies, proxy=None):
            self.cookies = cookies
            self.proxy = proxy

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def resolve_short_url(self, short_url):
            assert short_url == "https://v.douyin.com/demo"
            return "https://www.douyin.com/video/1234567890123456789"

    class _FakeDownloader:
        def __init__(self):
            self.artifact_records = [
                {
                    "aweme_id": "1234567890123456789",
                    "media_type": "video",
                    "output_dir": str(tmp_path),
                    "file_paths": [str(tmp_path / "demo.mp4")],
                    "file_names": ["demo.mp4"],
                }
            ]

        async def download(self, parsed_url):
            assert parsed_url["aweme_id"] == "1234567890123456789"
            result = DownloadResult()
            result.total = 1
            result.success = 1
            return result

    monkeypatch.setattr("engine_api.service.DouyinAPIClient", _FakeAPIClient)
    monkeypatch.setattr(
        "engine_api.service.URLParser.parse",
        lambda url: {
            "type": "video",
            "aweme_id": "1234567890123456789",
            "original_url": url,
        },
    )
    monkeypatch.setattr(
        "engine_api.service.DownloaderFactory.create",
        lambda *args, **kwargs: _FakeDownloader(),
    )

    request = SingleItemDownloadRequest(
        job_id="job-short-link",
        url="https://v.douyin.com/demo",
        output_dir=str(tmp_path),
        database=False,
    )
    response = run_single_item_download_sync(request, emitter=events.append)

    assert response.status == "success"
    assert response.aweme_id == "1234567890123456789"
    assert response.url_type == "video"
    assert response.resolved_url == "https://www.douyin.com/video/1234567890123456789"
    assert response.saved_files == [str(tmp_path / "demo.mp4")]
    assert response.file_names == ["demo.mp4"]
    assert [event["event"] for event in events] == [
        "job.started",
        "job.step",
        "job.url_resolved",
    ]


def test_single_item_service_rejects_unsupported_user_urls(monkeypatch, tmp_path):
    class _FakeAPIClient:
        def __init__(self, cookies, proxy=None):
            self.cookies = cookies
            self.proxy = proxy

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("engine_api.service.DouyinAPIClient", _FakeAPIClient)
    monkeypatch.setattr(
        "engine_api.service.URLParser.parse",
        lambda url: {
            "type": "user",
            "sec_uid": "demo-sec-uid",
            "original_url": url,
        },
    )

    request = SingleItemDownloadRequest(
        job_id="job-user-url",
        url="https://www.douyin.com/user/demo-sec-uid",
        output_dir=str(tmp_path),
        database=False,
    )
    response = run_single_item_download_sync(request)

    assert response.status == "failed"
    assert response.error_code == "unsupported_url_type"
    assert response.url_type == "user"
