"""Log in with the device's fingerprint or face check (WebAuthn passkeys).

The owner logs in once with the password and registers the phone. From then on the phone can log in
by itself: it signs a one-time challenge with a key that never leaves it (or its Google / iCloud
account), after its own fingerprint, face or screen-lock check. The server keeps only the public key.
"""

import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, generate_challenge
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..auth import check_login_rate, issue_session, record_failure, require_auth
from ..config import settings
from ..db import get_db
from ..models import Passkey
from ..schemas import MeOut, PasskeyCredentialIn, PasskeyOut

router = APIRouter(prefix="/auth/passkeys", tags=["auth"])

# One user. A phone that registers again replaces its old passkey instead of keeping two.
USER_ID = b"paprika-admin"

# Challenges handed out and not used yet: challenge -> expiry. Each one works once. In memory is
# enough because the API runs as a single process; a restart only means "try again".
CHALLENGE_SECONDS = 5 * 60
MAX_PENDING_CHALLENGES = 500
_challenges: dict[bytes, float] = {}
_challenges_lock = threading.Lock()


def _new_challenge() -> bytes:
    challenge = generate_challenge()
    now = time.time()
    with _challenges_lock:
        for old, expires in list(_challenges.items()):
            if expires < now:
                del _challenges[old]
        while len(_challenges) >= MAX_PENDING_CHALLENGES:
            del _challenges[next(iter(_challenges))]  # oldest first
        _challenges[challenge] = now + CHALLENGE_SECONDS
    return challenge


def _take_challenge(credential: dict) -> bytes:
    """The challenge the device signed, if this server issued it and nobody used it yet."""
    try:
        client_data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
        challenge = base64url_to_bytes(client_data["challenge"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "תשובה לא תקינה מהמכשיר") from None
    with _challenges_lock:
        expires = _challenges.pop(challenge, 0.0)
    if expires < time.time():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "עבר יותר מדי זמן. נסו שוב.")
    return challenge


def _relying_party(request: Request) -> tuple[str, str]:
    """(rp_id, origin) of the site as the browser sees it.

    PUBLIC_URL when set (production: the Netlify address, which proxies /api here). Without it
    (local development) the request's Origin header.
    """
    origin = settings.public_url.strip().rstrip("/") or request.headers.get("origin", "")
    host = urlparse(origin).hostname
    if not host:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "כתובת האתר לא ידועה (PUBLIC_URL)")
    return host, origin


def _device_name(user_agent: str) -> str:
    ua = user_agent.lower()
    for marker, name in (
        ("iphone", "אייפון"),
        ("ipad", "אייפד"),
        ("android", "טלפון אנדרואיד"),
        ("windows", "מחשב Windows"),
        ("macintosh", "מק"),
    ):
        if marker in ua:
            return name
    return "מכשיר"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _out(passkey: Passkey) -> PasskeyOut:
    return PasskeyOut(
        id=passkey.id,
        credential_id=bytes_to_base64url(passkey.credential_id),
        name=passkey.name,
        created_at=passkey.created_at,
        last_used_at=passkey.last_used_at,
    )


def _json(options) -> Response:
    return Response(options_to_json(options), media_type="application/json")


# ---------- Registering this device (needs a password login first) ----------


@router.get("", response_model=list[PasskeyOut], dependencies=[Depends(require_auth)])
def list_passkeys(db: Session = Depends(get_db)):
    return [_out(p) for p in db.scalars(select(Passkey).order_by(Passkey.created_at))]


@router.post("/register/options", dependencies=[Depends(require_auth)])
def register_options(request: Request, db: Session = Depends(get_db)):
    rp_id, _ = _relying_party(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.business_name,
        user_id=USER_ID,
        user_name=settings.business_name,
        challenge=_new_challenge(),
        authenticator_selection=AuthenticatorSelectionCriteria(
            # The device's own fingerprint / face sensor, not a USB key or another phone.
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            # Saved on the device, so logging in needs no user name.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # The browser refuses to register a device that already has one.
        exclude_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in db.scalars(select(Passkey))],
    )
    return _json(options)


@router.post("/register", response_model=PasskeyOut, dependencies=[Depends(require_auth)])
def register(body: PasskeyCredentialIn, request: Request, db: Session = Depends(get_db)):
    rp_id, origin = _relying_party(request)
    challenge = _take_challenge(body.credential)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except WebAuthnException:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ההפעלה נכשלה. נסו שוב.") from None

    existing = db.scalar(select(Passkey).where(Passkey.credential_id == verified.credential_id))
    if existing:
        return _out(existing)
    passkey = Passkey(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=_device_name(request.headers.get("user-agent", "")),
    )
    db.add(passkey)
    db.commit()
    return _out(passkey)


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_auth)])
def delete_passkey(passkey_id: int, db: Session = Depends(get_db)):
    passkey = db.get(Passkey, passkey_id)
    if passkey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "המכשיר לא נמצא")
    db.delete(passkey)
    db.commit()


# ---------- Logging in with it ----------


@router.post("/login/options")
def login_options(request: Request):
    rp_id, _ = _relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=_new_challenge(),
        # No list of credentials: the device offers the passkey it has for this site.
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return _json(options)


@router.post("/login", response_model=MeOut)
def login(body: PasskeyCredentialIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    check_login_rate(ip)
    rp_id, origin = _relying_party(request)
    challenge = _take_challenge(body.credential)
    try:
        credential_id = base64url_to_bytes(body.credential["rawId"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "תשובה לא תקינה מהמכשיר") from None

    passkey = db.scalar(select(Passkey).where(Passkey.credential_id == credential_id))
    if passkey is None:
        record_failure(ip)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "הכניסה עם טביעת אצבע הוסרה מהמכשיר הזה. היכנסו עם הסיסמה והפעילו אותה מחדש.",
        )
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except WebAuthnException:
        record_failure(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "הכניסה נכשלה. נסו שוב או היכנסו עם הסיסמה.") from None

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = datetime.now(timezone.utc)
    db.commit()
    issue_session(response)
    return MeOut(business_name=settings.business_name, grow_mode=settings.grow_mode)
