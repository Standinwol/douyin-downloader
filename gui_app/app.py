from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict, Iterable, Optional

from utils.cookie_utils import parse_cookie_header, sanitize_cookies

APP_TITLE = "Douyin Downloader Desktop"
DEFAULT_WINDOW_SIZE = "1180x780"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Downloaded"
DEFAULT_STATE_PATH = PROJECT_ROOT / ".gui-state.json"


def normalize_python_executable(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return raw
    candidate = Path(raw)
    if candidate.name.lower() == "pythonw.exe":
        python_exe = candidate.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return raw


def detect_worker_python(
    project_root: Path = PROJECT_ROOT,
    current_executable: Optional[str] = None,
) -> str:
    local_venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if local_venv_python.exists():
        return str(local_venv_python)

    current = normalize_python_executable(current_executable or sys.executable)
    if current:
        return current

    return "python"


def parse_cookie_text(raw_text: str) -> Dict[str, str]:
    text = str(raw_text or "").strip()
    if not text:
        return {}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        return sanitize_cookies(payload)
    if isinstance(payload, list):
        cookies: Dict[str, str] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if isinstance(name, str):
                cookies[name] = "" if value is None else str(value)
        return sanitize_cookies(cookies)

    return sanitize_cookies(parse_cookie_header(text))


def format_cookie_text(cookies: Dict[str, str]) -> str:
    return json.dumps(sanitize_cookies(cookies), ensure_ascii=False, indent=2)


def build_worker_request(
    *,
    url: str,
    output_dir: str,
    cookies: Dict[str, str],
    proxy: str = "",
    cover: bool = True,
    music: bool = True,
    avatar: bool = True,
    json_metadata: bool = True,
    database: bool = True,
) -> Dict[str, Any]:
    return {
        "url": str(url or "").strip(),
        "output_dir": str(output_dir or "").strip(),
        "cookies": sanitize_cookies(cookies),
        "proxy": str(proxy or "").strip(),
        "cover": bool(cover),
        "music": bool(music),
        "avatar": bool(avatar),
        "json": bool(json_metadata),
        "database": bool(database),
    }


def default_cookie_paths(project_root: Path = PROJECT_ROOT) -> Iterable[Path]:
    return (
        project_root / "config" / "cookies.json",
        project_root / ".cookies.json",
    )


def load_default_cookie_text(project_root: Path = PROJECT_ROOT) -> str:
    for path in default_cookie_paths(project_root):
        if path.exists():
            try:
                return format_cookie_text(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return ""


def load_gui_state(state_path: Path = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def save_gui_state(state: Dict[str, Any], state_path: Path = DEFAULT_STATE_PATH) -> None:
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class DouyinDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(1080, 700)

        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker_process: Optional[subprocess.Popen[str]] = None
        self.worker_request_file: Optional[Path] = None
        self.final_response: Optional[Dict[str, Any]] = None
        self.cancel_requested = False
        self.items_total = 1
        self.items_done = 0

        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.proxy_var = tk.StringVar()
        self.python_var = tk.StringVar(value=detect_worker_python())
        self.status_var = tk.StringVar(value="Ready")
        self.step_var = tk.StringVar(value="Enter a Douyin single video or gallery URL to begin.")
        self.summary_var = tk.StringVar(value="No downloads yet.")
        self.cover_var = tk.BooleanVar(value=True)
        self.music_var = tk.BooleanVar(value=True)
        self.avatar_var = tk.BooleanVar(value=True)
        self.json_var = tk.BooleanVar(value=True)
        self.database_var = tk.BooleanVar(value=True)

        self._configure_style()
        self._build_layout()
        self._restore_state()
        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        self.root.configure(bg="#f5efe8")
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background="#f5efe8")
        style.configure("Card.TLabelframe", background="#fbf8f4", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background="#fbf8f4", foreground="#76203a", font=("Segoe UI Semibold", 11))
        style.configure("App.TLabel", background="#f5efe8", foreground="#2a2230", font=("Segoe UI", 10))
        style.configure("Heading.TLabel", background="#f5efe8", foreground="#7a1237", font=("Segoe UI Semibold", 20))
        style.configure("Muted.TLabel", background="#f5efe8", foreground="#6b6370", font=("Segoe UI", 9))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10))
        style.configure("TCheckbutton", background="#fbf8f4", foreground="#2a2230")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor="#eadfd2",
            bordercolor="#eadfd2",
            background="#d93668",
            lightcolor="#d93668",
            darkcolor="#d93668",
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Stable desktop wrapper for the JSON worker API. Best for single video or gallery links.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        left = ttk.Frame(outer, style="App.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        right = ttk.Frame(outer, style="App.TFrame")
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_target_card(left).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._build_options_card(left).grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._build_cookie_card(left).grid(row=2, column=0, sticky="nsew")

        self._build_status_card(right).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._build_actions_card(right).grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._build_log_card(right).grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self._build_files_card(right).grid(row=3, column=0, sticky="nsew")

    def _build_target_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Download Target", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Douyin URL", style="App.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Output folder", style="App.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew")
        ttk.Button(frame, text="Browse...", command=self._choose_output_dir).grid(row=1, column=2, padx=(8, 0))

        ttk.Label(frame, text="Worker Python", style="App.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        python_entry = ttk.Entry(frame, textvariable=self.python_var)
        python_entry.grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(frame, text="Detect", command=self._reset_python_path).grid(row=2, column=2, padx=(8, 0), pady=(10, 0))

        return frame

    def _build_options_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Download Options", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Proxy", style="App.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.proxy_var).grid(row=0, column=1, sticky="ew")

        checks = ttk.Frame(frame, style="App.TFrame")
        checks.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for column in range(3):
            checks.columnconfigure(column, weight=1)

        ttk.Checkbutton(checks, text="Cover image", variable=self.cover_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(checks, text="Music track", variable=self.music_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(checks, text="Author avatar", variable=self.avatar_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(checks, text="Save JSON metadata", variable=self.json_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(checks, text="Track SQLite history", variable=self.database_var).grid(row=1, column=1, sticky="w", pady=(6, 0))

        return frame

    def _build_cookie_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Cookies", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Paste a cookie header or JSON object/list. Default cookie files can be loaded below.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")

        self.cookie_text = ScrolledText(frame, height=18, wrap="word", font=("Consolas", 10))
        self.cookie_text.grid(row=1, column=0, sticky="nsew", pady=(8, 10))

        buttons = ttk.Frame(frame, style="App.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="Load cookie file", command=self._load_cookie_file).pack(side="left")
        ttk.Button(buttons, text="Load defaults", command=self._load_default_cookies).pack(side="left", padx=8)
        ttk.Button(buttons, text="Clear", command=self._clear_cookies).pack(side="left")

        return frame

    def _build_status_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Status", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, textvariable=self.status_var, style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.step_var, style="App.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 10))

        self.progress = ttk.Progressbar(
            frame,
            mode="determinate",
            maximum=1,
            value=0,
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.grid(row=2, column=0, sticky="ew")
        ttk.Label(frame, textvariable=self.summary_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))
        return frame

    def _build_actions_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Actions", style="Card.TLabelframe", padding=14)

        self.download_button = ttk.Button(
            frame,
            text="Start Download",
            command=self._start_download,
            style="Primary.TButton",
        )
        self.download_button.pack(side="left")

        self.cancel_button = ttk.Button(frame, text="Cancel", command=self._cancel_download)
        self.cancel_button.pack(side="left", padx=8)
        self.cancel_button.state(["disabled"])

        ttk.Button(frame, text="Open output folder", command=self._open_output_folder).pack(side="left")
        return frame

    def _build_log_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Activity Log", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(frame, height=14, wrap="word", state="disabled", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        return frame

    def _build_files_card(self, parent: ttk.LabelFrame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Saved Files", style="Card.TLabelframe", padding=14)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.file_list = tk.Listbox(frame, activestyle="none", font=("Consolas", 10))
        self.file_list.grid(row=0, column=0, sticky="nsew")
        self.file_list.bind("<Double-Button-1>", self._open_selected_file)
        return frame

    def _restore_state(self) -> None:
        state = load_gui_state()
        if state.get("output_dir"):
            self.output_dir_var.set(str(state["output_dir"]))
        if state.get("proxy"):
            self.proxy_var.set(str(state["proxy"]))
        for key, variable in (
            ("cover", self.cover_var),
            ("music", self.music_var),
            ("avatar", self.avatar_var),
            ("json", self.json_var),
            ("database", self.database_var),
        ):
            if key in state:
                variable.set(bool(state[key]))

        default_cookies = load_default_cookie_text()
        if default_cookies:
            self.cookie_text.insert("1.0", default_cookies)
            self._append_log("Loaded cookies from the default cookie file.")

    def _save_state(self) -> None:
        save_gui_state(
            {
                "output_dir": self.output_dir_var.get().strip(),
                "proxy": self.proxy_var.get().strip(),
                "cover": self.cover_var.get(),
                "music": self.music_var.get(),
                "avatar": self.avatar_var.get(),
                "json": self.json_var.get(),
                "database": self.database_var.get(),
            }
        )

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose download folder",
            initialdir=self.output_dir_var.get().strip() or str(DEFAULT_OUTPUT_DIR),
        )
        if selected:
            self.output_dir_var.set(selected)

    def _reset_python_path(self) -> None:
        self.python_var.set(detect_worker_python())

    def _load_cookie_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Load cookies",
            filetypes=[
                ("JSON files", "*.json"),
                ("Text files", "*.txt;*.log"),
                ("All files", "*.*"),
            ],
            initialdir=str(PROJECT_ROOT),
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Cookie load failed", str(exc))
            return

        self.cookie_text.delete("1.0", "end")
        self.cookie_text.insert("1.0", content)
        self._append_log(f"Loaded cookies from {path}")

    def _load_default_cookies(self) -> None:
        content = load_default_cookie_text()
        if not content:
            messagebox.showinfo("No default cookies", "No config/cookies.json or .cookies.json file was found.")
            return
        self.cookie_text.delete("1.0", "end")
        self.cookie_text.insert("1.0", content)
        self._append_log("Loaded cookies from the default cookie file.")

    def _clear_cookies(self) -> None:
        self.cookie_text.delete("1.0", "end")

    def _set_running(self, running: bool) -> None:
        if running:
            self.download_button.state(["disabled"])
            self.cancel_button.state(["!disabled"])
        else:
            self.download_button.state(["!disabled"])
            self.cancel_button.state(["disabled"])

    def _reset_progress(self) -> None:
        self.items_total = 1
        self.items_done = 0
        self.progress.configure(maximum=1, value=0)

    def _start_download(self) -> None:
        if self.worker_process and self.worker_process.poll() is None:
            messagebox.showinfo("Download running", "Wait for the current download to finish or cancel it first.")
            return

        url = self.url_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        python_executable = normalize_python_executable(self.python_var.get())

        if not url:
            messagebox.showerror("Missing URL", "Enter a Douyin single video or gallery URL.")
            return
        if not output_dir:
            messagebox.showerror("Missing output folder", "Choose where the downloaded files should be stored.")
            return
        if not python_executable:
            messagebox.showerror("Missing Python", "The worker Python executable could not be determined.")
            return

        try:
            cookies = parse_cookie_text(self.cookie_text.get("1.0", "end"))
        except Exception as exc:
            messagebox.showerror("Cookie parse failed", str(exc))
            return

        if not cookies:
            proceed = messagebox.askyesno(
                "Run without cookies?",
                "No cookies were detected. Public links may still fail. Do you want to continue?",
            )
            if not proceed:
                return

        request_payload = build_worker_request(
            url=url,
            output_dir=output_dir,
            cookies=cookies,
            proxy=self.proxy_var.get(),
            cover=self.cover_var.get(),
            music=self.music_var.get(),
            avatar=self.avatar_var.get(),
            json_metadata=self.json_var.get(),
            database=self.database_var.get(),
        )

        self._save_state()
        self.final_response = None
        self.cancel_requested = False
        self._reset_progress()
        self.file_list.delete(0, "end")
        self.status_var.set("Running")
        self.step_var.set("Starting worker process...")
        self.summary_var.set("Waiting for the first worker event.")
        self._append_log(f"Launching worker for {url}")
        self._set_running(True)

        request_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        with request_file:
            json.dump(request_payload, request_file, ensure_ascii=False, indent=2)
        self.worker_request_file = Path(request_file.name)

        command = [
            python_executable,
            "-m",
            "engine_api.worker",
            "--request-file",
            str(self.worker_request_file),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.worker_process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            self._set_running(False)
            self.status_var.set("Failed")
            self.step_var.set("Worker launch failed.")
            self.summary_var.set(str(exc))
            messagebox.showerror("Worker launch failed", str(exc))
            self._cleanup_request_file()
            return

        threading.Thread(target=self._stream_stdout, daemon=True).start()
        threading.Thread(target=self._stream_stderr, daemon=True).start()
        threading.Thread(target=self._wait_for_worker, daemon=True).start()

    def _stream_stdout(self) -> None:
        assert self.worker_process is not None
        assert self.worker_process.stdout is not None
        for line in self.worker_process.stdout:
            self.event_queue.put(("stdout", line.rstrip("\n")))

    def _stream_stderr(self) -> None:
        assert self.worker_process is not None
        assert self.worker_process.stderr is not None
        for line in self.worker_process.stderr:
            self.event_queue.put(("stderr", line.rstrip("\n")))

    def _wait_for_worker(self) -> None:
        assert self.worker_process is not None
        return_code = self.worker_process.wait()
        self.event_queue.put(("exit", return_code))

    def _cancel_download(self) -> None:
        if not self.worker_process or self.worker_process.poll() is not None:
            return
        self.cancel_requested = True
        self.status_var.set("Cancelling")
        self.step_var.set("Stopping worker process...")
        self.summary_var.set("Cancellation requested.")
        self._append_log("Cancellation requested by user.")
        try:
            self.worker_process.terminate()
        except Exception as exc:
            self._append_log(f"Terminate failed: {exc}")

    def _handle_worker_event(self, payload: Dict[str, Any]) -> None:
        event = payload.get("event", "")
        if event == "job.started":
            self.step_var.set("Worker started.")
            self.summary_var.set("Preparing the download job.")
        elif event == "job.step":
            detail = str(payload.get("detail") or payload.get("step") or "").strip()
            self.step_var.set(detail or "Worker reported progress.")
            if detail:
                self._append_log(detail)
        elif event == "job.items_total":
            total = int(payload.get("total", 1) or 1)
            self.items_total = max(total, 1)
            self.items_done = 0
            self.progress.configure(maximum=self.items_total, value=0)
            self.summary_var.set(f"Tracking {self.items_total} item(s).")
        elif event == "job.item":
            self.items_done += 1
            self.progress.configure(value=min(self.items_done, self.items_total))
            status = str(payload.get("status") or "processed")
            detail = str(payload.get("detail") or "").strip()
            self.summary_var.set(
                f"Processed {min(self.items_done, self.items_total)} / {self.items_total} item(s)."
            )
            self._append_log(f"Item {status}: {detail or 'n/a'}")
        elif event == "job.url_resolved":
            resolved = str(payload.get("resolved_url") or "").strip()
            if resolved:
                self._append_log(f"Resolved short link to {resolved}")
        elif event in {"job.completed", "job.failed"}:
            response = payload.get("response")
            if isinstance(response, dict):
                self.final_response = response
                self._apply_final_response(response)
            else:
                self.status_var.set("Failed")
                self.step_var.set("Worker returned no response payload.")
                self.summary_var.set("The worker finished without a structured response.")

    def _apply_final_response(self, response: Dict[str, Any]) -> None:
        status = str(response.get("status") or "failed")
        saved_files = [str(path) for path in response.get("saved_files") or []]
        aweme_id = str(response.get("aweme_id") or "").strip()
        output_dir = str(response.get("output_dir") or self.output_dir_var.get()).strip()
        summary = (
            f"Success {response.get('success_count', 0)} / "
            f"Failed {response.get('failed_count', 0)} / "
            f"Skipped {response.get('skipped_count', 0)}"
        )

        if status == "success":
            self.status_var.set("Success")
            self.step_var.set(f"Downloaded aweme {aweme_id or 'unknown'}.")
            self.progress.configure(value=self.items_total)
        elif status == "skipped":
            self.status_var.set("Skipped")
            self.step_var.set("The target was already available locally.")
            self.progress.configure(value=self.items_total)
        else:
            self.status_var.set("Failed")
            error_message = str(response.get("error_message") or "Download failed.")
            self.step_var.set(error_message)

        self.summary_var.set(summary)
        self.file_list.delete(0, "end")
        for path in saved_files:
            self.file_list.insert("end", path)
        if saved_files:
            self._append_log(f"Saved {len(saved_files)} file(s) to {output_dir}")
        if response.get("error_code"):
            self._append_log(
                f"Worker error [{response.get('error_code')}]: {response.get('error_message')}"
            )

    def _handle_worker_exit(self, return_code: int) -> None:
        self._cleanup_request_file()
        process = self.worker_process
        self.worker_process = None
        self._set_running(False)

        if self.cancel_requested:
            self.status_var.set("Cancelled")
            self.step_var.set("The worker process was stopped.")
            self.summary_var.set("Cancelled before completion.")
            self._append_log("Worker cancelled.")
            self.cancel_requested = False
            return

        if self.final_response is None:
            if return_code == 0:
                self.status_var.set("Finished")
                self.step_var.set("Worker exited cleanly without a final payload.")
                self.summary_var.set("No structured response was received.")
            else:
                self.status_var.set("Failed")
                self.step_var.set("Worker exited unexpectedly.")
                self.summary_var.set(f"Exit code: {return_code}")
                self._append_log(f"Worker exited with code {return_code}.")
        elif process is not None and return_code != 0 and self.final_response.get("status") != "failed":
            self._append_log(f"Worker exited with code {return_code}.")

    def _cleanup_request_file(self) -> None:
        if self.worker_request_file and self.worker_request_file.exists():
            try:
                self.worker_request_file.unlink()
            except OSError:
                pass
        self.worker_request_file = None

    def _poll_events(self) -> None:
        if not self.root.winfo_exists():
            return
        try:
            while True:
                event_type, payload = self.event_queue.get_nowait()
                if event_type == "stdout":
                    self._handle_stdout_line(str(payload))
                elif event_type == "stderr":
                    if payload:
                        self._append_log(f"stderr: {payload}")
                elif event_type == "exit":
                    self._handle_worker_exit(int(payload))
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_events)

    def _handle_stdout_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            self._append_log(f"stdout: {line}")
            return
        self._handle_worker_event(payload)

    def _open_output_folder(self) -> None:
        target = None
        if self.final_response and self.final_response.get("output_dir"):
            target = self.final_response.get("output_dir")
        else:
            target = self.output_dir_var.get().strip()
        if not target:
            return
        self._open_path(target)

    def _open_selected_file(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.file_list.curselection()
        if not selection:
            return
        value = self.file_list.get(selection[0])
        self._open_path(value)

    def _open_path(self, target: str) -> None:
        path = Path(str(target or "")).resolve()
        if not path.exists():
            messagebox.showinfo("Path not found", f"{path} does not exist yet.")
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def _on_close(self) -> None:
        if self.worker_process and self.worker_process.poll() is None:
            should_close = messagebox.askyesno(
                "Download in progress",
                "A download is still running. Close the window and stop the worker?",
            )
            if not should_close:
                return
            self._cancel_download()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    app = DouyinDownloaderApp(root)
    root.mainloop()
    return 0
