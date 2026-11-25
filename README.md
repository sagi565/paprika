# פפריקה – ניהול חיובים חודשיים

Monthly billing site for Paprika fruit & vegetables: kindergartens, monthly amounts,
one-click charging through Grow, and sending each invoice image on WhatsApp.

Stack: React + Vite (frontend, served by nginx) · FastAPI · PostgreSQL · Docker Compose.

## Run

```bash
cp .env.example .env      # then change every "change-me"
docker compose up -d --build
```

Open http://localhost:8080 and log in with `ADMIN_PASSWORD` from `.env`.

With `SEED_DEMO=true` an empty database is filled with demo kindergartens.
To start over: `docker compose down -v` (deletes the database and invoice images).

## Login

One password (`ADMIN_PASSWORD`), or the device's fingerprint / face check (WebAuthn passkeys,
[backend/app/routers/passkeys.py](backend/app/routers/passkeys.py)). After a password login on a
phone, the site offers to enable the fingerprint; from then on that phone's login page starts with
**כניסה עם טביעת אצבע**, and the password still works everywhere. **טביעת אצבע** in the top bar
lists the registered devices and removes a lost one. Only public keys are stored (`passkeys` table).

A login lasts `SESSION_HOURS` (default 12). Passkeys are bound to the site's domain, taken from
`PUBLIC_URL` (or the request's `Origin` when it is empty, e.g. locally); a new domain means
enabling the fingerprint again. Browsers allow passkeys only over HTTPS or on `localhost`.

## How it works

0. **בית** – dashboard: this month's progress, revenue tiles, revenue by month
   (6/12/24 months, chart or table) and the top kindergartens of the year.
   With `SEED_DEMO=true`, 11 months of sent charges are added so the chart has data.
1. **גנים** – add kindergartens one by one or import a CSV (Hebrew headers; a template
   is downloadable on the page). Each one needs a saved Grow card token to be charged.
2. **חיובים** – pick the month, type each kindergarten's amount, press
   **חיוב כל הגנים**. Rows are claimed atomically (`pending/failed → processing`) so
   nothing is charged twice; the page refreshes while the charges run.
3. After a successful charge the invoice is fetched and stored as one PNG (see **Invoices**).
   Click the thumbnail to see it; **הורדה** saves it.
4. **שליחה בוואטסאפ** sends the image straight from the business's own WhatsApp to the
   kindergarten's phone, once WhatsApp is linked (**וואטסאפ** in the top bar, see below).
   **שליחת כל החשבוניות** sends the whole month, a few seconds apart. A sent row becomes
   **נשלח**; a failed one shows why and offers **שליחה חוזרת**.
   Without a linked WhatsApp, the button opens the send page instead: on a phone over HTTPS
   it opens the share sheet with the image attached; otherwise download + open chat.

## Invoices

Grow documents an invoice link only through a notification (`invoiceNotifyUrl` / the
dashboard's "invoice created" webhook), not for token charges. So the site tries, in order:

1. Grow's notification, kept in `grow_invoice_notices` even when it arrives before our
   charge request has returned, and matched by `transactionId`, `transactionCode` or `asmachta`.
2. `getTransactionInfo` for the charge (the fields it returns are logged, so they can be checked).
3. A background check repeats this every 3 minutes for the first hour, then every 30 minutes,
   for two weeks. **הבאת חשבונית** runs it at once.

The link is turned into a picture: a PDF or image is converted; a web page is searched for its
PDF, and otherwise printed by headless Chromium. If Grow's invoice never comes, **העלאה** takes
the owner's own PDF or photo of it.

## WhatsApp

Sending uses [wacli](https://github.com/openclaw/wacli) (unofficial, WhatsApp Web protocol),
installed in the backend image at a pinned version checked by SHA-256. The owner links it
once from **וואטסאפ** in the top bar: with a pairing code typed in WhatsApp (works on the
same phone) or a QR code (when the site is open on a computer). It appears in WhatsApp under
Linked devices and can be removed there or with **ניתוק**.

wacli's session (`session.db`) is copied into the database (`whatsapp_session`) after every
run and written back on startup, so a redeploy doesn't unlink it. One wacli process runs at
a time. Only a little chat history is kept on the server while linking (1 day, 200 messages).

If the server restarts in the middle of a charge, that row becomes **נכשל** with a
note to check Grow before charging again.

## Grow

`GROW_MODE=mock` simulates Grow end to end (fake transactions, sample invoice).
`GROW_MODE=live` uses `LiveGrowGateway` in [backend/app/services/grow.py](backend/app/services/grow.py):

| Step | Grow API |
|---|---|
| Save a card (once per kindergarten) | `createPaymentProcess` with `chargeType=3`, `saveCardToken=1`; opened after ticking the terms and card-consent boxes. Grow posts the token to `/api/grow/notify` (client id + HMAC in `cField1`/`cField2`). |
| Approve | After the card-save notification, `approveTransaction` with the pageCode and the notification data. Only for the card save; token charges are never approved |
| Monthly charge | `createTransactionWithToken`, `paymentType=2`, with only `transactionUniqueIdentifier` (kept across a retry after an unknown outcome, so Grow refuses to charge twice; on error 1010 the earlier attempt is looked up) |
| Invoice | Grow posts `invoiceUrl` to `/api/grow/invoice-notify`; the PDF/image is turned into the PNG sent on WhatsApp |

Webhook URLs carry `?key=GROW_WEBHOOK_KEY`. Still to confirm with Grow: whether token
charges send `invoiceNotifyUrl` invoices, and whether `getTransactionInfo` returns the
invoice link for them (the server log line `getTransactionInfo … fields:` shows what it returns).

Docs: https://developers.grow.business

## Going online

Hosted setup (free, HTTPS): Netlify (frontend, proxies `/api/*`) + Render (API, `render.yaml`)
+ Neon (Postgres). Step-by-step guide in Hebrew: [DEPLOY.md](DEPLOY.md).

Invoice images are stored in Postgres (`invoice_images`), so the API keeps no state on disk.

## Development without Docker

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload   # needs DATABASE_URL, SECRET_KEY, ADMIN_PASSWORD
cd frontend && npm install && npm run dev                                        # proxies /api to :8000
```
