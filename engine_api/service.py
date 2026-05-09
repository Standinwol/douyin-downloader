from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, URLParser
from storage import Database, FileManager

from .contracts import SingleItemDownloadRequest, SingleItemDownloadResponse
from .runtime import EventProgressReporter, RuntimeConfig, RuntimeCookieManager

SUPPORTED_WORKER_URL_TYPES = {"video", "gallery", "user", "collection", "music"}


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


def _collect_response_artifacts(
    artifacts: Any,
    *,
    fallback_output_dir: str,
    url_type: str,
    parsed_url: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    parsed_url = parsed_url or {}
    normalized_artifacts = [
        artifact for artifact in (artifacts or []) if isinstance(artifact, dict)
    ]
    saved_files = []
    file_names = []
    output_dirs = []
    aweme_ids = []
    media_types = []

    for artifact in normalized_artifacts:
        saved_files.extend(
            str(path)
            for path in artifact.get("file_paths") or []
            if isinstance(path, str) and path.strip()
        )
        file_names.extend(
            str(name)
            for name in artifact.get("file_names") or []
            if isinstance(name, str) and name.strip()
        )
        output_dir = artifact.get("output_dir")
        if isinstance(output_dir, str) and output_dir.strip():
            output_dirs.append(output_dir)

        aweme_id = artifact.get("aweme_id")
        if isinstance(aweme_id, str) and aweme_id.strip():
            aweme_ids.append(aweme_id)

        media_type = artifact.get("media_type")
        if isinstance(media_type, str) and media_type.strip():
            media_types.append(media_type)

    output_dir = str(fallback_output_dir or "").strip()
    if output_dirs:
        try:
            output_dir = os.path.commonpath(output_dirs)
        except ValueError:
            output_dir = output_dirs[-1]

    aweme_id = ""
    if len(set(aweme_ids)) == 1:
        aweme_id = aweme_ids[0]
    elif len(normalized_artifacts) <= 1:
        aweme_id = str(
            parsed_url.get("aweme_id") or parsed_url.get("note_id") or ""
        ).strip()

    unique_media_types = {
        str(media_type).strip() for media_type in media_types if str(media_type).strip()
    }
    if len(unique_media_types) == 1:
        media_type = next(iter(unique_media_types))
    elif unique_media_types:
        media_type = "mixed"
    elif url_type == "gallery":
        media_type = "gallery"
    elif url_type == "video":
        media_type = "video"
    else:
        media_type = ""

    return {
        "aweme_id": aweme_id,
        "media_type": media_type,
        "output_dir": output_dir,
        "saved_files": saved_files,
        "file_names": file_names,
    }


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
            if url_type not in SUPPORTED_WORKER_URL_TYPES:
                return _failure_response(
                    request,
                    error_code="unsupported_url_type",
                    error_message=(
                        "Unsupported URL type for the desktop worker API"
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
            artifact_summary = _collect_response_artifacts(
                artifacts,
                fallback_output_dir=str(config.get("path")),
                url_type=url_type,
                parsed_url=parsed_url,
            )

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
                aweme_id=str(artifact_summary["aweme_id"]),
                media_type=str(artifact_summary["media_type"]),
                output_dir=str(artifact_summary["output_dir"]),
                saved_files=list(artifact_summary["saved_files"]),
                file_names=list(artifact_summary["file_names"]),
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
