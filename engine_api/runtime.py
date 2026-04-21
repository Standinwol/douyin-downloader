from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, Optional

from config.default_config import DEFAULT_CONFIG
from utils.cookie_utils import sanitize_cookies


class RuntimeConfig:
    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        if initial:
            self.update(**initial)

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if isinstance(self.config.get(key), dict) and isinstance(value, dict):
                self.config[key] = self._merge_dicts(self.config[key], value)
            else:
                self.config[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    @staticmethod
    def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = RuntimeConfig._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result


class RuntimeCookieManager:
    def __init__(self, cookies: Optional[Dict[str, str]] = None):
        self._cookies = sanitize_cookies(cookies or {})

    def get_cookies(self) -> Dict[str, str]:
        return dict(self._cookies)

    def validate_cookies(self) -> bool:
        required = {"ttwid", "odin_tt", "passport_csrf_token"}
        return all(self._cookies.get(key) for key in required)


class EventProgressReporter:
    def __init__(
        self,
        *,
        job_id: str,
        emitter: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.job_id = job_id
        self.emitter = emitter

    def update_step(self, step: str, detail: str = "") -> None:
        self._emit("job.step", step=step, detail=detail)

    def set_item_total(self, total: int, detail: str = "") -> None:
        self._emit("job.items_total", total=total, detail=detail)

    def advance_item(self, status: str, detail: str = "") -> None:
        self._emit("job.item", status=status, detail=detail)

    def _emit(self, event: str, **payload: Any) -> None:
        if not self.emitter:
            return
        self.emitter(
            {
                "event": event,
                "job_id": self.job_id,
                **payload,
            }
        )
