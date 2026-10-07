"""Central settings. Every value can be overridden with an environment variable."""
import os

def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))

MAX_FILES = _int("DOCSHIFT_MAX_FILES", 5)            # per request, all tools except merge
MAX_MERGE_FILES = _int("DOCSHIFT_MAX_MERGE_FILES", 20)
MAX_FILE_MB = _int("DOCSHIFT_MAX_FILE_MB", 25)       # per uploaded file
MAX_TOTAL_MB = _int("DOCSHIFT_MAX_TOTAL_MB", 100)    # per request
MAX_CONCURRENT_JOBS = _int("DOCSHIFT_MAX_CONCURRENT_JOBS", 4)  # busy slots across all users
RATE_LIMIT_PER_MIN = _int("DOCSHIFT_RATE_LIMIT_PER_MIN", 30)   # requests per IP per minute
CONVERT_TIMEOUT_S = _int("DOCSHIFT_CONVERT_TIMEOUT_S", 120)    # LibreOffice / Ghostscript
