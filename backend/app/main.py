"""Docshift API. Run with:  uvicorn app.main:app --reload   (from the backend folder)."""
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, converters as cv
from .utils import JobSlot, RateLimiter, bundle, read_uploads, stem

app = FastAPI(title="Docshift", version="1.0.0")
limiter = RateLimiter(config.RATE_LIMIT_PER_MIN)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method == "POST":
        try:
            limiter.check(request.client.host if request.client else "unknown")
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


@app.exception_handler(cv.ConversionError)
async def conversion_error(_: Request, exc: cv.ConversionError):
    return JSONResponse({"detail": str(exc)}, status_code=422)


def respond(results: list[tuple[str, bytes]], note: str = "") -> Response:
    name, data, mime = bundle(results)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
               "X-Filename": quote(name), "X-Note": quote(note),
               "Access-Control-Expose-Headers": "X-Filename, X-Note"}
    return Response(data, media_type=mime, headers=headers)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/limits")
def limits():
    return {"max_files": config.MAX_FILES, "max_merge_files": config.MAX_MERGE_FILES,
            "max_file_mb": config.MAX_FILE_MB, "max_total_mb": config.MAX_TOTAL_MB}


@app.post("/api/images-to-pdf")
def images_to_pdf(files: list[UploadFile] = File(...), mode: str = Form("one"), size: str = Form("a4")):
    items = read_uploads(files, "image", config.MAX_FILES)
    with JobSlot():
        if mode == "separate":
            return respond([(stem(n) + ".pdf", cv.images_to_pdf([d], size)) for n, d in items])
        return respond([("images.pdf" if len(items) > 1 else stem(items[0][0]) + ".pdf",
                         cv.images_to_pdf([d for _, d in items], size))])


@app.post("/api/pdf-to-word")
def pdf_to_word(files: list[UploadFile] = File(...)):
    items = read_uploads(files, "pdf", config.MAX_FILES)
    with JobSlot():
        return respond([(stem(n) + ".docx", cv.pdf_to_docx(d)) for n, d in items])


@app.post("/api/word-to-pdf")
def word_to_pdf(files: list[UploadFile] = File(...)):
    items = read_uploads(files, "docx", config.MAX_FILES)
    with JobSlot():
        return respond([(stem(n) + ".pdf", cv.docx_to_pdf(d)) for n, d in items])


@app.post("/api/compress")
def compress(files: list[UploadFile] = File(...), level: str = Form("balanced")):
    items = read_uploads(files, "pdf", config.MAX_FILES)
    with JobSlot():
        results, notes = [], []
        for n, d in items:
            out, note = cv.compress_pdf(d, level)
            results.append((stem(n) + "-compressed.pdf", out))
            notes.append(f"{n}: {note}")
        return respond(results, " ".join(notes))


@app.post("/api/merge")
def merge(files: list[UploadFile] = File(...)):
    items = read_uploads(files, "pdf", config.MAX_MERGE_FILES)
    if len(items) < 2:
        raise HTTPException(400, "Add at least two PDFs to merge.")
    with JobSlot():
        return respond([("merged.pdf", cv.merge_pdfs(items))], f"{len(items)} files merged.")


# The frontend is plain static files, served by the same app. Must be mounted last.
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
