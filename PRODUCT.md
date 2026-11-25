# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The owner of פפריקה פירות וירקות, a greengrocer in Ramat Gan that supplies fresh produce to municipal kindergartens (Ramat Gan, Kiryat Ono, Givat Shmuel). He uses the site on his phone and on a computer about equally, usually once a month for the charge run and then while sending invoices.

Kindergarten teachers see only the public pages: the card-saved confirmation after Grow's card page, and the terms page.

## Product Purpose

Monthly billing for the kindergartens: keep the list of kindergartens, type each one's amount for the month, charge them all through Grow with their saved cards, and send each invoice image to the teacher on WhatsApp. Success is a month where every kindergarten is charged and every invoice is sent, without retyping card details or chasing paper.

## Positioning

A one-person tool built around one business's real monthly ritual: charge everyone in one tap, then work through WhatsApp sends one kindergarten after another. Not a general invoicing product.

## Operating Context

- Charges go through Grow (Meshulam): saved card tokens, token charges, invoices from Grow turned into PNG images.
- Invoices reach teachers on WhatsApp, through the phone's share sheet or by download plus open chat.
- Login is one password or the device's fingerprint/face (passkeys).
- Grow's site review requires the business details, contact phone and a terms link on every page (footer) and a public terms page.

## Capabilities and Constraints

- Hebrew only, right to left.
- Statuses per kindergarten per month: ממתין, מחייב…, חויב, נכשל, נשלח.
- Demo mode (`GROW_MODE=mock`) simulates Grow and shows a notice strip.
- Free hosting can sleep; the site shows a "server is waking up" notice while it retries.

## Brand Commitments

- Name: פפריקה פירות וירקות.
- Colour: paprika red, confirmed by the user (the business card's yellow and green were not chosen for the site).
- Logo: the wordmark "פפריקה" whose first letter is drawn as a red pepper; used on the site only (site logo, browser-tab icon, phone home-screen icon). Sources in `brand/`.

## Evidence on Hand

- Business details in `frontend/src/business.ts` (owner, business number, address, phone, email).
- The printed business card (yellow card, green lettering, fruit-basket photo) outside the repository.
- No testimonials, customer counts or other claims exist; none should be invented.

## Product Principles

1. The month's state must be readable at a glance: who is charged, who failed, whose invoice is still unsent.
2. Never risk a double charge; anything uncertain asks before charging again.
3. Phone first for the WhatsApp run, but the computer must be just as comfortable.
4. Card numbers are typed only on Grow's page and never pass through this site.

## Accessibility & Inclusion

The main user is not technical: large tap targets, plain Hebrew labels, clear status words next to every colour.
