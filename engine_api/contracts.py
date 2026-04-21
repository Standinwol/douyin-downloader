from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class SingleItemDownloadRequest:
    url: str
    output_dir: str
    cookies: Dict[str, str] = field(default_factory=dict)
    job_id: str = field(default_factory=lambda: uuid4().hex)
    proxy: str = ""
    thread: int = 5
    retry_times: int = 3
    rate_limit: float = 2.0
    cover: bool = True
    music: bool = True
    avatar: bool = True
    json: bool = True
    folderstyle: bool = True
    database: bool = True
    database_path: str = ""
    transcript: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "SingleItemDownloadRequest":
        payload = dict(payload or {})
        return cls(
            url=str(payload.get("url", "")).strip(),
            output_dir=str(payload.get("output_dir", "")).strip(),
            cookies=dict(payload.get("cookies") or {}),
            job_id=str(payload.get("job_id") or uuid4().hex),
            proxy=str(payload.get("proxy", "") or "").strip(),
            thread=int(payload.get("thread", 5) or 5),
            retry_times=int(payload.get("retry_times", 3) or 3),
            rate_limit=float(payload.get("rate_limit", 2) or 2),
            cover=bool(payload.get("cover", True)),
            music=bool(payload.get("music", True)),
            avatar=bool(payload.get("avatar", True)),
            json=bool(payload.get("json", True)),
            folderstyle=bool(payload.get("folderstyle", True)),
            database=bool(payload.get("database", True)),
            database_path=str(payload.get("database_path", "") or "").strip(),
            transcript=dict(payload.get("transcript") or {}),
        )

    def validate(self) -> Optional[str]:
        if not self.url:
            return "url is required"
        if not self.output_dir:
            return "output_dir is required"
        if self.thread < 1:
            return "thread must be >= 1"
        if self.retry_times < 0:
            return "retry_times must be >= 0"
        if self.rate_limit <= 0:
            return "rate_limit must be > 0"
        return None

    def resolved_database_path(self) -> str:
        if self.database_path:
            return self.database_path
        return str(Path(self.output_dir) / ".engine-state" / "dy_downloader.db")

    def to_safe_config(self) -> Dict[str, Any]:
        return {
            "path": self.output_dir,
            "cover": self.cover,
            "music": self.music,
            "avatar": self.avatar,
            "json": self.json,
            "folderstyle": self.folderstyle,
            "thread": self.thread,
            "retry_times": self.retry_times,
            "rate_limit": self.rate_limit,
            "proxy": self.proxy,
            "database": self.database,
            "database_path": self.resolved_database_path(),
            "transcript": dict(self.transcript),
        }


@dataclass
class SingleItemDownloadResponse:
    job_id: str
    status: str
    request_url: str
    resolved_url: str = ""
    url_type: str = ""
    aweme_id: str = ""
    media_type: str = ""
    output_dir: str = ""
    saved_files: List[str] = field(default_factory=list)
    file_names: List[str] = field(default_factory=list)
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "request_url": self.request_url,
            "resolved_url": self.resolved_url,
            "url_type": self.url_type,
            "aweme_id": self.aweme_id,
            "media_type": self.media_type,
            "output_dir": self.output_dir,
            "saved_files": list(self.saved_files),
            "file_names": list(self.file_names),
            "total": self.total,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
