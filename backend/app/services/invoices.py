"""Turns Grow's invoice (a PDF, an image or a web page) into one PNG image, the picture that is
shown on the site and sent on WhatsApp, and stores it."""

import html
import io
import logging
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pymupdf
from PIL import Image, ImageChops
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Charge, InvoiceImage
from .grow import InvoiceSource

log = logging.getLogger(__name__)

RENDER_DPI = 150
THUMB_WIDTH = 160
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
# A link or embed in the invoice page that points at the PDF itself.
_PDF_LINK = re.compile(r"""(?:href|src|data)\s*=\s*["']([^"']+?(?:\.pdf|/pdf|[?&](?:format|type)=pdf|download)[^"']*)["']""", re.I)


class NotADocument(ValueError):
    """The bytes are neither a PDF nor an image."""


def pdf_to_png(pdf: bytes) -> bytes:
    """Render every page and stack them vertically into one image."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages = [
            Image.open(io.BytesIO(page.get_pixmap(dpi=RENDER_DPI).tobytes("png"))).convert("RGB")
            for page in doc
        ]
    if not pages:
        raise ValueError("empty PDF")
    width = max(p.width for p in pages)
    sheet = Image.new("RGB", (width, sum(p.height for p in pages)), "white")
    y = 0
    for page in pages:
        sheet.paste(page, (0, y))
        y += page.height
    sheet = _trim_bottom(sheet)
    buf = io.BytesIO()
    sheet.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _trim_bottom(sheet: Image.Image, margin: int = 48) -> Image.Image:
    """Drop the empty white end of the last page, so the phone shows the invoice, not paper."""
    box = ImageChops.difference(sheet, Image.new("RGB", sheet.size, "white")).getbbox()
    if box is None:
        return sheet
    bottom = min(sheet.height, box[3] + margin)
    return sheet.crop((0, 0, sheet.width, bottom)) if bottom < sheet.height - margin else sheet


def document_to_png(data: bytes) -> bytes:
    """A PDF or an image (from Grow, or uploaded by the owner) to a PNG."""
    if data[:5] == b"%PDF-":
        return pdf_to_png(data)
    try:
        with Image.open(io.BytesIO(data)) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "PNG", optimize=True)
    except Exception:
        raise NotADocument("not a PDF or an image") from None
    return buf.getvalue()


def source_to_png(source: InvoiceSource) -> bytes:
    if source.data is not None:
        return document_to_png(source.data)
    if not source.url:
        raise ValueError("no invoice source")
    return url_to_png(source.url)


def _get(url: str) -> httpx.Response:
    if not url.startswith("https://"):
        raise ValueError(f"unexpected invoice URL: {url}")
    res = httpx.get(url, follow_redirects=True, timeout=30)
    res.raise_for_status()
    if len(res.content) > MAX_DOCUMENT_BYTES:
        raise ValueError("invoice document too large")
    return res


def url_to_png(url: str) -> bytes:
    """Grow's invoice link: a PDF or image is converted; a web page is searched for its PDF,
    and otherwise opened in a headless browser and printed, which gives the same picture."""
    try:
        res = _get(url)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403, 429):
            raise
        # Some sites refuse plain downloads but serve a real browser.
        log.info("Invoice link refused a download (%s); opening it in Chromium", exc.response.status_code)
        return pdf_to_png(print_page(url))
    try:
        return document_to_png(res.content)
    except NotADocument:
        pass
    page_url = str(res.url)
    for link in _PDF_LINK.findall(res.text)[:5]:
        pdf_url = urljoin(page_url, html.unescape(link))
        try:
            return document_to_png(_get(pdf_url).content)
        except Exception as exc:
            log.info("Invoice page link %s is not the document: %s", pdf_url, exc)
    return pdf_to_png(print_page(page_url))


def print_page(url: str) -> bytes:
    """Open a page in headless Chromium and print it to PDF (all of it, not just one screen)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page.pdf"
        cmd = [
            settings.chromium_bin,
            "--headless",
            "--no-sandbox",  # the container's user can't use Chromium's sandbox
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--lang=he-IL",
            f"--user-data-dir={tmp}/profile",
            "--no-pdf-header-footer",
            "--virtual-time-budget=15000",  # let the page's scripts draw the invoice
            f"--print-to-pdf={out}",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=90, check=True)
        except FileNotFoundError:
            raise RuntimeError("Chromium is not installed; cannot render the invoice page") from None
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Chromium produced no PDF")
        return out.read_bytes()


def make_thumbnail(png: bytes) -> bytes:
    with Image.open(io.BytesIO(png)) as img:
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2))
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def store_invoice(db: Session, ch: Charge, png: bytes) -> None:
    """Save (or replace) the charge's invoice image. The caller commits."""
    key = uuid.uuid4().hex[:8]
    row = db.get(InvoiceImage, ch.id)
    if row is None:
        row = InvoiceImage(charge_id=ch.id)
        db.add(row)
    row.key, row.image, row.thumb = key, png, make_thumbnail(png)
    ch.invoice_image = key


def import_legacy_files(db: Session) -> None:
    """One-off: images saved on disk by earlier versions move into the database."""
    folder = settings.data_dir / "invoices"
    rows = db.scalars(
        select(Charge).where(Charge.invoice_image.like("%.png"), Charge.id.not_in(select(InvoiceImage.charge_id)))
    ).all()
    for ch in rows:
        path = folder / Path(ch.invoice_image).name
        if path.exists():
            store_invoice(db, ch, path.read_bytes())
        else:
            ch.invoice_image = None
    if rows:
        db.commit()
        log.info("Moved %d invoice images into the database", len(rows))
