from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .contracts import SingleItemDownloadRequest
from .service import run_single_item_download_sync


def _emit_stdout(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read_request_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.request_file:
        return json.loads(Path(args.request_file).read_text(encoding="utf-8"))

    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("No JSON request provided on stdin")
    return json.loads(raw)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stable JSON worker for single-item Douyin downloads",
    )
    parser.add_argument(
        "--request-file",
        help="Path to a JSON request file. If omitted, JSON is read from stdin.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        payload = _read_request_payload(args)
        request = SingleItemDownloadRequest.from_mapping(payload)
    except Exception as exc:
        _emit_stdout(
            {
                "event": "job.failed",
                "status": "failed",
                "error_code": "invalid_request_payload",
                "error_message": str(exc),
            }
        )
        return 1

    response = run_single_item_download_sync(request, emitter=_emit_stdout)
    final_event = "job.completed" if response.status != "failed" else "job.failed"
    _emit_stdout(
        {
            "event": final_event,
            "job_id": response.job_id,
            "response": response.to_dict(),
        }
    )
    return 0 if response.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
