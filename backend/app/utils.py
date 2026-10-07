"""Upload validation, rate limiting, and small helpers shared by the routes."""
import io
import threading
import time
import zipfile
from collections import defaultdict, deque
from pathlib import Path

from fastapi import HTTPException, UploadFile

from . import config

MB = 1024 * 1024
# Magic bytes: we check file content, not just the extension.
SIGNATURES = {"pdf": b"%PDF", "docx": b"PK\x03\x04"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

# One semaphore shared by every user: caps how many heavy jobs run at once.
_jobs = threading.BoundedSemaphore(config.MAX_CONCURRENT_JOBS)


class JobSlot:
    """Context manager that rejects the request with 503 when the server is full."""

    def __enter__(self):
        if not _jobs.acquire(blocking=False):
            raise HTTPException(503, "The server is busy right now. Please try again in a minute.")

    def __exit__(self, *exc):
        _jobs.release()


class RateLimiter:
    """Sliding-window limiter, per client IP, kept in memory."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, ip: str) -> None:
        now = time.monotonic()
        with self.lock:
            q = self.hits[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
            q.append(now)


def read_uploads(files: list[UploadFile], kind: str, max_files: int) -> list[tuple[str, bytes]]:
    """Validate and read uploads. kind is 'pdf', 'docx' or 'image'. Returns (name, bytes) pairs."""
    if not files:
        raise HTTPException(400, "Add at least one file.")
    if len(files) > max_files:
        raise HTTPException(400, f"The limit is {max_files} files at once. You sent {len(files)}.")
    out, total = [], 0
    for f in files:
        name = Path(f.filename or "file").name
        data = f.file.read(config.MAX_FILE_MB * MB + 1)
        if len(data) > config.MAX_FILE_MB * MB:
            raise HTTPException(413, f"{name} is larger than {config.MAX_FILE_MB} MB.")
        total += len(data)
        if total > config.MAX_TOTAL_MB * MB:
            raise HTTPException(413, f"Files total more than {config.MAX_TOTAL_MB} MB.")
        if not data:
            raise HTTPException(400, f"{name} is empty.")
        ext = Path(name).suffix.lower()
        if kind == "image":
            if ext not in IMAGE_EXTS:
                raise HTTPException(400, f"{name} is not a supported image.")
        elif ext != f".{kind}" or not data.startswith(SIGNATURES[kind]):
            raise HTTPException(400, f"{name} is not a valid .{kind} file.")
        out.append((name, data))
    return out


def stem(name: str) -> str:
    return Path(name).stem


def bundle(results: list[tuple[str, bytes]]) -> tuple[str, bytes, str]:
    """One result -> (name, bytes, mime). Several results -> a ZIP."""
    mimes = {".pdf": "application/pdf",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if len(results) == 1:
        name, data = results[0]
        return name, data, mimes[Path(name).suffix]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        used = set()
        for name, data in results:
            n, i = name, 1
            while n in used:  # avoid duplicate names inside the zip
                n = f"{stem(name)}-{i}{Path(name).suffix}"; i += 1
            used.add(n)
            z.writestr(n, data)
    return "docshift-results.zip", buf.getvalue(), "application/zip"
