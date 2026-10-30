from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..auth import check_login_rate, clear_session, issue_session, require_auth, verify_password
from ..config import settings
from ..schemas import LoginIn, MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    check_login_rate(ip)
    if not verify_password(ip, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "סיסמה שגויה")
    issue_session(response)
    return MeOut(business_name=settings.business_name, grow_mode=settings.grow_mode)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    clear_session(response)


@router.get("/me", response_model=MeOut, dependencies=[Depends(require_auth)])
def me():
    return MeOut(business_name=settings.business_name, grow_mode=settings.grow_mode)
