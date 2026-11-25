"""Sends invoice images from the business's own WhatsApp number, through wacli.

wacli (https://github.com/openclaw/wacli) joins the owner's WhatsApp as a linked device, like
WhatsApp Web. The owner links it once from the site, with a pairing code or a QR code. wacli
keeps its keys in session.db; we copy that file into the database after every run, so a
redeploy (which wipes the server's disk) doesn't unlink it.

One wacli process runs at a time: they would share the same store.
"""

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from sqlalchemy import or_, update
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..db import SessionLocal
from ..models import Charge, ChargeStatus, InvoiceImage, WhatsAppSession

log = logging.getLogger(__name__)

STORE_DIR = settings.data_dir / "wacli"
SESSION_FILES = ("session.db", "session.db-wal", "session.db-shm")
PAIR_TIMEOUT = 240  # seconds a pairing may take before we stop it
SEND_TIMEOUT = 150
SEND_GAP = 4  # seconds between sends in a batch; WhatsApp flags rapid-fire senders

NOT_LINKED = "וואטסאפ לא מחובר. מחברים אותו מהכפתור וואטסאפ בראש האתר."
UNSURE_HINT = "בדקו בצ׳אט עם הגננת אם ההודעה יצאה לפני ששולחים שוב."

_run_lock = threading.Lock()  # one wacli process at a time
_state_lock = threading.Lock()


class WhatsAppError(Exception):
    """A send or link failed. The message is shown to the user (Hebrew)."""


@dataclass
class Pairing:
    method: str  # "qr" or "code"
    phone: str | None
    proc: subprocess.Popen | None = None
    qr: str | None = None
    code: str | None = None
    connected: bool = False  # the phone approved; wacli is finishing its first sync
    error: str | None = None
    cancelled: bool = False
    done: bool = False
    started: float = field(default_factory=time.monotonic)


_pairing: Pairing | None = None


# ---------- helpers ----------


def available() -> bool:
    return shutil.which(settings.wacli_bin) is not None


def international(phone: str) -> str:
    """0501234567 / 050-123-4567 / +972 50... -> 972501234567"""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return digits


def _env() -> dict:
    return {
        **os.environ,
        "WACLI_STORE_DIR": str(STORE_DIR),
        # Linking asks the phone for recent chats; keep only a little of it on the server.
        "WACLI_SYNC_MAX_MESSAGES": "200",
        "WACLI_SYNC_MAX_DB_SIZE": "20MB",
    }


def _envelope(stdout: str) -> dict:
    """wacli --json prints {"success": bool, "data": ..., "error": str|None}."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _run(args: list[str], timeout: float) -> dict:
    """Run wacli with JSON output. Caller holds _run_lock."""
    try:
        res = subprocess.run(
            [settings.wacli_bin, "--json", *args],
            env=_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise WhatsAppError("וואטסאפ לא ענה בזמן. " + UNSURE_HINT) from None
    except FileNotFoundError:
        raise WhatsAppError("wacli לא מותקן בשרת") from None
    env = _envelope(res.stdout)
    if res.returncode != 0 or not env.get("success", False):
        message = env.get("error") or res.stderr.strip()[-300:] or f"wacli exit {res.returncode}"
        log.warning("wacli %s failed: %s", args[0], message)
        env = {"success": False, "error": str(message), "data": env.get("data")}
    return env


def _is_logged_out(message: str) -> bool:
    text = message.lower()
    return "not authenticated" in text or "logged out" in text or "logged_out" in text


# ---------- session kept in the database ----------


def _clear_local() -> None:
    for name in SESSION_FILES:
        (STORE_DIR / name).unlink(missing_ok=True)


def _pack() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in SESSION_FILES:
            path = STORE_DIR / name
            if path.exists():
                tar.add(path, arcname=name)
    return buf.getvalue()


def _unpack(data: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name in SESSION_FILES and member.isfile():
                src = tar.extractfile(member)
                if src is not None:
                    (STORE_DIR / member.name).write_bytes(src.read())


def _save(db: Session, phone: str | None = None) -> None:
    row = db.get(WhatsAppSession, 1)
    if row is None:
        row = WhatsAppSession(id=1, data=b"")
        db.add(row)
    row.data = _pack()
    if phone:
        row.phone = phone
    db.commit()


def _forget(db: Session) -> None:
    row = db.get(WhatsAppSession, 1)
    if row is not None:
        db.delete(row)
        db.commit()
    _clear_local()


def restore_session() -> None:
    """On startup: the server's disk may be fresh, so write the saved session back."""
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        _clear_local()
        with SessionLocal() as db:
            row = db.get(WhatsAppSession, 1)
            if row is not None and row.data:
                _unpack(row.data)
                log.info("WhatsApp session restored (%s)", row.phone or "unknown number")
    except Exception:
        log.exception("Restoring the WhatsApp session failed")


# ---------- status and linking ----------


def status(db: Session) -> dict:
    row = db.get(WhatsAppSession, 1)
    out: dict = {
        "available": available(),
        "linked": row is not None,
        "phone": row.phone if row else None,
        "linked_at": row.linked_at if row else None,
        "pairing": None,
    }
    with _state_lock:
        p = _pairing
        if p is not None and (not p.done or time.monotonic() - p.started < PAIR_TIMEOUT + 30):
            out["pairing"] = {
                "method": p.method,
                "qr": p.qr,
                "code": p.code,
                "connected": p.connected,
                "error": p.error,
                "done": p.done,
            }
    return out


def start_pairing(method: str, phone: str | None) -> None:
    global _pairing
    if not available():
        raise WhatsAppError("wacli לא מותקן בשרת")
    with _state_lock:
        if _pairing is not None and not _pairing.done:
            if _pairing.method == method and _pairing.phone == phone:
                return  # already running; the page keeps polling it
            _pairing.cancelled = True
            _stop(_pairing)
            # Its watcher thread releases the run lock once wacli has exited.
        with SessionLocal() as db:
            if db.get(WhatsAppSession, 1) is not None:
                raise WhatsAppError("וואטסאפ כבר מחובר. כדי לחבר מספר אחר, מנתקים קודם.")
        if not _run_lock.acquire(timeout=20):
            raise WhatsAppError("וואטסאפ עסוק כרגע בשליחה. נסו שוב בעוד דקה.")
        try:
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            _clear_local()
            args = [
                settings.wacli_bin, "--json", "--events", "auth",
                "--history-days", "1", "--history-max-per-chat", "1", "--idle-exit", "15s",
            ]
            if method == "code":
                args += ["--phone", "+" + international(phone or "")]
            proc = subprocess.Popen(
                args,
                env=_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            _run_lock.release()
            raise
        _pairing = Pairing(method=method, phone=phone, proc=proc)
        threading.Thread(target=_watch_pairing, args=(_pairing,), daemon=True).start()


def cancel_pairing() -> None:
    with _state_lock:
        if _pairing is not None and not _pairing.done:
            _pairing.cancelled = True
            _stop(_pairing)


def _stop(p: Pairing) -> None:
    if p.proc is not None and p.proc.poll() is None:
        p.proc.kill()


def _watch_pairing(p: Pairing) -> None:
    assert p.proc is not None and p.proc.stderr is not None and p.proc.stdout is not None
    timer = threading.Timer(PAIR_TIMEOUT, lambda: None if p.connected else _stop(p))
    timer.start()
    try:
        for line in p.proc.stderr:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            name, data = event.get("event"), event.get("data") or {}
            if name == "qr_code":
                p.qr = data.get("code")
            elif name == "pair_code":
                p.code = data.get("code")
            elif name == "connected":
                p.connected = True
            elif name == "error":
                p.error = str(data.get("message") or "שגיאה")
        returncode = p.proc.wait()
        env = _envelope(p.proc.stdout.read())
        result = env.get("data") if isinstance(env.get("data"), dict) else env
        if returncode == 0 and result.get("authenticated"):
            phone = _linked_phone()
            with SessionLocal() as db:
                _save(db, phone)
            log.info("WhatsApp linked (%s)", phone)
        else:
            _clear_local()
            if p.cancelled:
                p.error = None
            elif not p.error:
                p.error = "הזמן לחיבור נגמר. נסו שוב." if not p.connected else "החיבור לא הושלם. נסו שוב."
            log.info("WhatsApp pairing ended without a link: %s", "cancelled" if p.cancelled else p.error)
    except Exception:
        log.exception("WhatsApp pairing failed")
        p.error = p.error or "החיבור נכשל. נסו שוב."
        _clear_local()
    finally:
        timer.cancel()
        p.done = True
        _run_lock.release()


def _linked_phone() -> str | None:
    """Caller holds _run_lock."""
    env = _run(["auth", "status"], timeout=30)
    data = env.get("data") or {}
    return str(data.get("phone") or "") or None


def logout() -> None:
    with _run_lock:
        if available() and (STORE_DIR / "session.db").exists():
            env = _run(["--lock-wait", "30s", "auth", "logout"], timeout=60)
            if not env.get("success"):
                log.warning("wacli logout: %s (forgetting the session anyway)", env.get("error"))
        with SessionLocal() as db:
            _forget(db)


# ---------- sending ----------


def caption(ch: Charge) -> str:
    from .billing import month_label  # billing imports nothing from here; avoids a cycle at import time

    hello = f"שלום {ch.client.contact_name}," if ch.client.contact_name else "שלום,"
    amount = ""
    if ch.amount is not None:
        value = float(ch.amount)
        amount = f" ({value:,.0f} ₪)" if value == int(value) else f" ({value:,.2f} ₪)"
    return f"{hello}\nמצורפת החשבונית של {settings.business_name} לחודש {month_label(ch.month)}{amount}.\nתודה!"


def _as_jpeg(png: bytes) -> bytes:
    """WhatsApp shows photos as JPEG; a sharp JPEG keeps the invoice text readable."""
    with Image.open(io.BytesIO(png)) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
    return buf.getvalue()


def send_image(phone: str, image_png: bytes, text: str) -> str | None:
    """Send one photo with a caption. Returns WhatsApp's message id. Raises WhatsAppError."""
    to = international(phone)
    if not re.fullmatch(r"9725\d{8}", to):
        raise WhatsAppError("לגן אין מספר נייד (05X), ולכן אי אפשר לשלוח לו בוואטסאפ. עדכנו את הטלפון בעמוד הגנים.")
    with _run_lock:
        with SessionLocal() as db:
            if db.get(WhatsAppSession, 1) is None:
                raise WhatsAppError(NOT_LINKED)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invoice.jpg"
            path.write_bytes(_as_jpeg(image_png))
            env = _run(
                [
                    "--lock-wait", "30s", "send", "file",
                    "--to", "+" + to, "--file", str(path), "--as", "image",
                    "--caption", text, "--post-send-wait", "3s",
                ],
                timeout=SEND_TIMEOUT,
            )
        with SessionLocal() as db:
            if not env.get("success"):
                error = str(env.get("error") or "")
                if _is_logged_out(error):
                    _forget(db)
                    raise WhatsAppError("וואטסאפ התנתק מהאתר (אולי הוסר בטלפון). מחברים אותו מחדש מהכפתור וואטסאפ.")
                if (STORE_DIR / "session.db").exists():
                    _save(db)
                raise WhatsAppError(f"השליחה בוואטסאפ נכשלה ({error[:200]}). {UNSURE_HINT}")
            _save(db)  # the session's keys move on with every connection
    data = env.get("data") or {}
    return str(data.get("id") or data.get("message_id") or "") or None


def claim(db: Session, *conditions) -> list[int]:
    """Atomically queue charged rows that have an invoice image, so none is sent twice."""
    stmt = (
        update(Charge)
        .where(
            Charge.status == ChargeStatus.CHARGED,
            Charge.invoice_image.is_not(None),
            or_(Charge.wa_state.is_(None), Charge.wa_state == "failed"),
            *conditions,
        )
        .values(wa_state="queued", wa_error=None)
        .returning(Charge.id)
        .execution_options(synchronize_session=False)
    )
    ids = list(db.scalars(stmt))
    db.commit()
    return ids


def send_many(charge_ids: list[int]) -> None:
    for i, charge_id in enumerate(charge_ids):
        if i:
            time.sleep(SEND_GAP)
        send_charge(charge_id)


def send_charge(charge_id: int) -> None:
    """Send one queued row's invoice to the kindergarten. Runs in background tasks."""
    with SessionLocal() as db:
        ch = db.get(Charge, charge_id, options=[joinedload(Charge.client)])
        if ch is None or ch.wa_state != "queued":
            return
        img = db.get(InvoiceImage, ch.id)
        if img is None:
            ch.wa_state, ch.wa_error = "failed", "אין תמונת חשבונית"
            db.commit()
            return
        ch.wa_state = "sending"
        db.commit()
        try:
            message_id = send_image(ch.client.phone, img.image, caption(ch))
        except WhatsAppError as exc:
            ch.wa_state, ch.wa_error = "failed", str(exc)
            db.commit()
            return
        except Exception:
            log.exception("WhatsApp send failed unexpectedly (charge %s)", charge_id)
            ch.wa_state, ch.wa_error = "failed", "השליחה נכשלה. " + UNSURE_HINT
            db.commit()
            return
        ch.status, ch.sent_at = ChargeStatus.SENT, datetime.now(timezone.utc)
        ch.wa_state, ch.wa_error, ch.wa_message_id = None, None, message_id
        db.commit()
        log.info("Invoice of charge %s sent on WhatsApp", charge_id)


def recover_interrupted(db: Session) -> None:
    """A restart mid-batch: queued rows weren't sent; a row that was sending may have gone out."""
    db.execute(update(Charge).where(Charge.wa_state == "queued").values(wa_state=None))
    db.execute(
        update(Charge)
        .where(Charge.wa_state == "sending")
        .values(wa_state="failed", wa_error="השרת הופעל מחדש באמצע השליחה. " + UNSURE_HINT)
    )
    db.commit()
