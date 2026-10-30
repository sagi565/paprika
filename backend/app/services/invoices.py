"""Turns invoice PDFs into a single PNG image (the "screenshot" sent on WhatsApp) and stores it."""

import io
import logging
import uuid
from pathlib import Path

import pymupdf
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Charge, InvoiceImage

log = logging.getLogger(__name__)

RENDER_DPI = 150
THUMB_WIDTH = 160


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
    buf = io.BytesIO()
    sheet.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def document_to_png(data: bytes) -> bytes:
    """Invoice from Grow, as PDF or as an image, to a PNG."""
    if data[:5] == b"%PDF-":
        return pdf_to_png(data)
    with Image.open(io.BytesIO(data)) as img:  # raises if it isn't an image either
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


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
