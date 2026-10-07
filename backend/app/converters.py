"""Pure conversion functions: bytes in, bytes out. No web code here, so they are easy to test."""
import io
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from . import config


class ConversionError(Exception):
    """A problem with the user's file. The message is safe to show to them."""


A4_PX = (1240, 1754)  # A4 at 150 dpi
GS_LEVELS = {"high": "/printer", "balanced": "/ebook", "small": "/screen"}


def _open_image(data: bytes) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    except Exception as exc:
        raise ConversionError("The image could not be read.") from exc


def images_to_pdf(images: list[bytes], page_size: str = "a4") -> bytes:
    pages = []
    for data in images:
        img = _open_image(data)
        if page_size == "a4":
            m = 60
            img.thumbnail((A4_PX[0] - 2 * m, A4_PX[1] - 2 * m))
            page = Image.new("RGB", A4_PX, "white")
            page.paste(img, ((A4_PX[0] - img.width) // 2, (A4_PX[1] - img.height) // 2))
            img = page
        pages.append(img)
    out = io.BytesIO()
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150.0, quality=90)
    return out.getvalue()


def pdf_to_docx(data: bytes) -> bytes:
    from pdf2docx import Converter  # imported lazily: it is slow to import

    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in.pdf"), Path(tmp, "out.docx")
        src.write_bytes(data)
        cv = Converter(str(src))
        try:
            cv.convert(str(dst))
        except Exception as exc:
            raise ConversionError("The PDF could not be converted. It may be damaged or password-protected.") from exc
        finally:
            cv.close()
        if not dst.exists():
            raise ConversionError("No text could be extracted. Scanned PDFs need OCR, which is not supported.")
        return dst.read_bytes()


def docx_to_pdf(data: bytes) -> bytes:
    if not shutil.which("soffice"):
        raise ConversionError("LibreOffice is not installed on the server.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp, "in.docx")
        src.write_bytes(data)
        # A private profile per run lets several conversions happen at the same time.
        profile = Path(tmp, f"profile-{uuid.uuid4().hex}").as_uri()
        cmd = ["soffice", f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
               "--outdir", tmp, str(src)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=config.CONVERT_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("The conversion took too long.") from exc
        except subprocess.CalledProcessError as exc:
            raise ConversionError("The Word file could not be converted.") from exc
        out = Path(tmp, "in.pdf")
        if not out.exists():
            raise ConversionError("The Word file could not be converted.")
        return out.read_bytes()


def compress_pdf(data: bytes, level: str = "balanced") -> tuple[bytes, str]:
    """Returns (pdf_bytes, note). Never returns something bigger than the input."""
    if not shutil.which("gs"):
        raise ConversionError("Ghostscript is not installed on the server.")
    setting = GS_LEVELS.get(level, "/ebook")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in.pdf"), Path(tmp, "out.pdf")
        src.write_bytes(data)
        cmd = ["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5", f"-dPDFSETTINGS={setting}",
               "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={dst}", str(src)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=config.CONVERT_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("The compression took too long.") from exc
        except subprocess.CalledProcessError as exc:
            raise ConversionError("The PDF could not be compressed. It may be damaged or password-protected.") from exc
        out = dst.read_bytes()
    if len(out) >= len(data):
        return data, "Already compact, so the original was kept."
    saved = round((1 - len(out) / len(data)) * 100)
    return out, f"{saved}% smaller."


def merge_pdfs(pdfs: list[tuple[str, bytes]]) -> bytes:
    writer = PdfWriter()
    for name, data in pdfs:
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ConversionError(f"{name} is password-protected.")
            for page in reader.pages:
                writer.add_page(page)
        except PyPdfError as exc:
            raise ConversionError(f"{name} could not be read. It may be damaged.") from exc
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
