# Docshift

A web app that converts JPEG/PNG images to PDF, PDF to Word, and Word to PDF, compresses PDFs, and merges PDFs.
Built with FastAPI (Python) and a plain JavaScript frontend.

| Tool | Limit per request | Engine |
|---|---|---|
| Images to PDF | 5 files | Pillow |
| PDF to Word | 5 files | pdf2docx |
| Word to PDF | 5 files | LibreOffice |
| Compress PDF | 5 files | Ghostscript |
| Merge PDFs | 20 files | pypdf |

## Project layout

```
docshift/
  backend/
    app/
      main.py         API routes, rate limiting, serves the frontend
      converters.py   conversion functions (bytes in, bytes out)
      utils.py        upload validation, job slots, rate limiter, zip bundling
      config.py       limits, overridable with environment variables
    tests/test_api.py API tests (pytest)
    requirements.txt  runtime dependencies
    requirements-dev.txt  adds test dependencies
  frontend/           index.html, app.js, styles.css
  Dockerfile
```

## Run with Docker (easiest, includes LibreOffice and Ghostscript)

```bash
docker build -t docshift .
docker run -p 8000:8000 docshift
```
Open http://localhost:8000

## Run locally without Docker

Install the system programs first: LibreOffice and Ghostscript
(Ubuntu: `sudo apt install libreoffice-writer ghostscript`).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000 and the interactive API docs at http://localhost:8000/docs

## Run the tests

```bash
cd backend
python -m pytest
```
Tests for Word to PDF and compression are skipped automatically if LibreOffice or Ghostscript is missing.

## How multiple users are handled

- Every request is independent and keeps files only in memory or in a private temporary folder that is deleted afterwards. Nothing is stored.
- LibreOffice runs with a separate profile per conversion, so simultaneous users do not clash.
- A shared job limit (`DOCSHIFT_MAX_CONCURRENT_JOBS`, default 4) returns "server busy" instead of crashing under load.
- A per-IP rate limit (`DOCSHIFT_RATE_LIMIT_PER_MIN`, default 30) protects against abuse.
- Uploads are checked by size, count, extension and file signature.

## Configuration

Set these environment variables to change limits: `DOCSHIFT_MAX_FILES`, `DOCSHIFT_MAX_MERGE_FILES`,
`DOCSHIFT_MAX_FILE_MB`, `DOCSHIFT_MAX_TOTAL_MB`, `DOCSHIFT_MAX_CONCURRENT_JOBS`,
`DOCSHIFT_RATE_LIMIT_PER_MIN`, `DOCSHIFT_CONVERT_TIMEOUT_S`.

## Known limitations

- Scanned PDFs cannot be converted to Word (no OCR).
- PDF to Word keeps text and basic layout, but complex layouts may shift.
- The rate limiter is in memory, so it is per process. With several servers, move it to Redis.
- No accounts or history yet.

## Possible next steps

User accounts and conversion history (PostgreSQL), background job queue (Celery or RQ) for large files,
OCR for scanned PDFs, and deployment behind HTTPS with a reverse proxy.
