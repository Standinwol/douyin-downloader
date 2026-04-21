from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from control import QueueManager, RateLimiter, RetryHandler
from core import DownloaderFactory, DouyinAPIClient, URLParser
from storage import Database, FileManager

from .contracts import SingleItemDownloadRequest, SingleItemDownloadResponse
from .runtime import EventProgressReporter, RuntimeConfig, RuntimeCookieManager

SUPPORTED_SINGLE_ITEM_TYPES = {"video", "gallery"}


def _emit(
    emitter: Optional[Callable[[Dict[str, Any]], None]],
    event: str,
    **payload: Any,
) -> None:
    if not emitter:
        return
    emitter({"event": event, **payload})


def _build_runtime_config(request: SingleItemDownloadRequest) -> RuntimeConfig:
    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = RuntimeConfig(
        {
            "path": str(output_dir),
            "cover": request.cover,
            "music": request.music,
            "avatar": request.avatar,
            "json": request.json,
            "folderstyle": request.folderstyle,
            "thread": request.thread,
            "retry_times": request.retry_times,
            "rate_limit": request.rate_limit,
            "proxy": request.proxy,
            "database": request.database,
            "database_path": request.resolved_database_path(),
            "transcript": dict(request.transcript),
        }
    )
    return config


def _failure_response(
    request: SingleItemDownloadRequest,
    *,
    error_code: str,
    error_message: str,
    resolved_url: str = "",
    url_type: str = "",
    aweme_id: str = "",
) -> SingleItemDownloadResponse:
    return SingleItemDownloadResponse(
        job_id=request.job_id,
        status="failed",
        request_url=request.url,
        resolved_url=resolved_url,
        url_type=url_type,
        aweme_id=aweme_id,
        error_code=error_code,
        error_message=error_message,
    )


async def run_single_item_download(
    request: SingleItemDownloadRequest,
    *,
    emitter: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> SingleItemDownloadResponse:
    validation_error = request.validate()
    if validation_error:
        return _failure_response(
            request,
            error_code="invalid_request",
            error_message=validation_error,
        )

    config = _build_runtime_config(request)
    cookie_manager = RuntimeCookieManager(request.cookies)
    file_manager = FileManager(config.get("path"))
    rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
    retry_handler = RetryHandler(max_retries=int(config.get("retry_times", 3) or 3))
    queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))
    progress_reporter = EventProgressReporter(job_id=request.job_id, emitter=emitter)

    database = None
    if request.database:
        database_path = Path(request.resolved_database_path()).resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        database = Database(db_path=str(database_path))
        await database.initialize()

    resolved_url = request.url
    parsed_url: Optional[Dict[str, Any]] = None

    _emit(
        emitter,
        "job.started",
        job_id=request.job_id,
        request_url=request.url,
        output_dir=str(Path(request.output_dir).resolve()),
    )

    try:
        async with DouyinAPIClient(
            cookie_manager.get_cookies(),
            proxy=config.get("proxy"),
        ) as api_client:
            if request.url.startswith("https://v.douyin.com"):
                progress_reporter.update_step("resolve_url", "Resolving short link")
                short_resolved = await api_client.resolve_short_url(request.url)
                if not short_resolved:
                    return _failure_response(
                        request,
                        error_code="short_url_resolve_failed",
                        error_message="Failed to resolve short Douyin URL",
                    )
                resolved_url = short_resolved
                _emit(
                    emitter,
                    "job.url_resolved",
                    job_id=request.job_id,
                    request_url=request.url,
                    resolved_url=resolved_url,
                )

            parsed_url = URLParser.parse(resolved_url)
            if not parsed_url:
                return _failure_response(
                    request,
                    error_code="url_parse_failed",
                    error_message="Unsupported or invalid Douyin URL",
                    resolved_url=resolved_url,
                )

            url_type = str(parsed_url.get("type") or "")
            if url_type not in SUPPORTED_SINGLE_ITEM_TYPES:
                return _failure_response(
                    request,
                    error_code="unsupported_url_type",
                    error_message=(
                        "Only single video and gallery links are supported by the stable worker API"
                    ),
                    resolved_url=resolved_url,
                    url_type=url_type,
                    aweme_id=str(parsed_url.get("aweme_id") or ""),
                )

            downloader = DownloaderFactory.create(
                url_type,
                config,
                api_client,
                file_manager,
                cookie_manager,
                database,
                rate_limiter,
                retry_handler,
                queue_manager,
                progress_reporter=progress_reporter,
            )
            if downloader is None:
                return _failure_response(
                    request,
                    error_code="downloader_not_found",
                    error_message=f"No downloader found for URL type: {url_type}",
                    resolved_url=resolved_url,
                    url_type=url_type,
                    aweme_id=str(parsed_url.get("aweme_id") or ""),
                )

            result = await downloader.download(parsed_url)
            artifacts = getattr(downloader, "artifact_records", [])
            primary_artifact = artifacts[-1] if artifacts else {}

            if database is not None:
                await database.add_history(
                    {
                        "url": request.url,
                        "url_type": url_type,
                        "total_count": result.total,
                        "success_count": result.success,
                        "config": str(request.to_safe_config()),
                    }
                )

            response = SingleItemDownloadResponse(
                job_id=request.job_id,
                status=(
                    "success"
                    if result.success > 0
                    else "skipped"
                    if result.skipped > 0 and result.failed == 0
                    else "failed"
                ),
                request_url=request.url,
                resolved_url=resolved_url,
                url_type=url_type,
                aweme_id=str(
                    primary_artifact.get("aweme_id")
                    or parsed_url.get("aweme_id")
                    or parsed_url.get("note_id")
                    or ""
                ),
                media_type=str(
                    primary_artifact.get("media_type")
                    or ("gallery" if url_type == "gallery" else "video")
                ),
                output_dir=str(primary_artifact.get("output_dir") or config.get("path")),
                saved_files=list(primary_artifact.get("file_paths") or []),
                file_names=list(primary_artifact.get("file_names") or []),
                total=result.total,
                success_count=result.success,
                failed_count=result.failed,
                skipped_count=result.skipped,
                error_code="" if result.success > 0 or result.skipped > 0 else "download_failed",
                error_message=(
                    ""
                    if result.success > 0 or result.skipped > 0
                    else "The downloader finished without a successful artifact"
                ),
            )
            return response
    except Exception as exc:
        return _failure_response(
            request,
            error_code="internal_error",
            error_message=str(exc),
            resolved_url=resolved_url,
            url_type=str((parsed_url or {}).get("type") or ""),
            aweme_id=str((parsed_url or {}).get("aweme_id") or ""),
        )
    finally:
        if database is not None:
            await database.close()


def run_single_item_download_sync(
    request: SingleItemDownloadRequest,
    *,
    emitter: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> SingleItemDownloadResponse:
    return asyncio.run(run_single_item_download(request, emitter=emitter))
