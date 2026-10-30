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

## How it works

0. **בית** – dashboard: this month's progress, revenue tiles, revenue by month
   (6/12/24 months, chart or table) and the top kindergartens of the year.
   With `SEED_DEMO=true`, 11 months of sent charges are added so the chart has data.
1. **גנים** – add kindergartens one by one or import a CSV (Hebrew headers; a template
   is downloadable on the page). Each one needs a saved Grow card token to be charged.
2. **חיובים** – pick the month, type each kindergarten's amount, press
   **חיוב כל הגנים**. Rows are claimed atomically (`pending/failed → processing`) so
   nothing is charged twice; the page refreshes while the charges run.
3. After a successful charge the invoice PDF is fetched, rendered to a PNG and stored.
4. **שליחה בוואטסאפ** opens a phone-friendly page with the image. On a phone over HTTPS
   it opens the share sheet with the image attached (choose WhatsApp → the teacher);
   otherwise it offers download + open-chat. Sending marks the row **נשלח**, and
   **לגן הבא** jumps to the next unsent one.

If the server restarts in the middle of a charge, that row becomes **נכשל** with a
note to check Grow before charging again.

## What is still missing: Grow

`GROW_MODE=mock` simulates Grow end to end (fake transactions, sample invoice).
The real integration is `LiveGrowGateway` in
[backend/app/services/grow.py](backend/app/services/grow.py). Fill in three methods:

| Method | What it should do |
|---|---|
| `charge_with_token` | `createTransactionWithToken` with the saved token and the amount; raise `ChargeFailed("<Hebrew reason>")` on decline |
| `fetch_invoice_pdf` | download the invoice PDF for the transaction (ask Grow where the document link comes from) |
| `start_card_save` | `createPaymentProcess` with `chargeType=3`, `saveCardToken=1`; return the page URL |

Plus the webhook stub in [backend/app/routers/grow_webhook.py](backend/app/routers/grow_webhook.py)
(Grow sends the saved token there). Then set `GROW_MODE=live` and the `GROW_*` values.
Everything else (PDF → PNG, storage, statuses, UI) already works.

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
