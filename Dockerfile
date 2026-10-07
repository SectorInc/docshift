FROM python:3.12-slim

# LibreOffice (Word to PDF) and Ghostscript (PDF compression) are system programs, not Python packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer ghostscript fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend

# Run as a normal user, not root.
RUN useradd -m app && chown -R app /srv
USER app
WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
