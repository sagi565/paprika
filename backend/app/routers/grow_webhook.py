from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/grow", tags=["grow"])


@router.post("/notify")
async def grow_notify(request: Request):
    """Grow's server-to-server notifications (notifyUrl). Not behind login: Grow calls it.

    TODO(grow): verify the request really comes from Grow, then
    - after a card-save page: store the card token on the matching client;
    - after a transaction: approve it (approveTransaction) and keep the invoice link.
    """
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "not implemented yet")
