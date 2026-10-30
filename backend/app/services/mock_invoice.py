"""Draws a sample invoice for mock mode. Not used with the real Grow integration."""

from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from ..config import settings

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WIDTH, HEIGHT = 1240, 1754  # A4 at 150 dpi
MARGIN = 110
INK = (31, 29, 26)
MUTED = (119, 113, 106)
LINE = (232, 227, 220)
ACCENT = (181, 65, 44)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    # BASIC layout + python-bidi gives correct right-to-left Hebrew without libraqm.
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def _rtl(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill=INK) -> None:
    draw.text((WIDTH - MARGIN, y), get_display(text), font=font, fill=fill, anchor="ra")


def _ltr(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill=INK) -> None:
    draw.text((MARGIN, y), get_display(text), font=font, fill=fill, anchor="la")


def render_mock_invoice(raw: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(img)
    title, big, body, small = _font(FONT_BOLD, 54), _font(FONT_BOLD, 40), _font(FONT, 32), _font(FONT, 26)
    customer = raw.get("customer", {})

    d.rectangle((0, 0, WIDTH, 16), fill=ACCENT)
    _rtl(d, 110, settings.business_name, title)
    _rtl(d, 190, "חשבונית מס / קבלה", body, MUTED)
    _ltr(d, 120, f"מס׳ {raw.get('invoice_number', '')}", body)
    _ltr(d, 170, raw.get("date", ""), body, MUTED)
    d.line((MARGIN, 270, WIDTH - MARGIN, 270), fill=LINE, width=3)

    _rtl(d, 310, "לכבוד", small, MUTED)
    _rtl(d, 350, customer.get("invoice_name") or customer.get("name", ""), big)
    if customer.get("tax_id"):
        _rtl(d, 410, f"ח.פ {customer['tax_id']}", body, MUTED)

    d.line((MARGIN, 500, WIDTH - MARGIN, 500), fill=LINE, width=3)
    _rtl(d, 530, "תיאור", small, MUTED)
    _ltr(d, 530, "סכום", small, MUTED)
    _rtl(d, 590, raw.get("description", ""), body)
    _ltr(d, 590, f"₪{float(raw.get('amount', 0)):,.2f}", body)
    d.line((MARGIN, 670, WIDTH - MARGIN, 670), fill=LINE, width=3)
    _rtl(d, 700, "סה״כ לתשלום", big)
    _ltr(d, 700, f"₪{float(raw.get('amount', 0)):,.2f}", big, ACCENT)

    _rtl(d, 820, f"אסמכתא: {raw.get('transaction_id', '')}", small, MUTED)
    _rtl(d, HEIGHT - 150, "מסמך לדוגמה (מצב בדיקה). אינו חשבונית אמיתית.", small, MUTED)
    return img
