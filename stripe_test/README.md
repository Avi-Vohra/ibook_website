# Stripe one-time payment demo (Streamlit + Checkout)

Self-contained Streamlit app that accepts a one-time $20 payment with Stripe
Checkout, persists Stripe IDs in a local SQLite database, and confirms payment
via the `checkout.session.completed` webhook (handled by a small companion
Flask receiver, since Streamlit can't accept webhook POSTs).

## Setup

```bash
cd stripe_test
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# make sure .env has your keys from https://dashboard.stripe.com/apikeys
```

## Run (three terminals — all required)

```bash
streamlit run streamlit_app.py                     # the UI
python webhook_server.py                           # webhook receiver on :4242
stripe listen --forward-to localhost:4242/webhook  # copy whsec_... into .env
```

## Try it

1. In the Streamlit app, click **Create Checkout Session** and open the
   Checkout link.
2. Pay with test card `4242 4242 4242 4242`, any future expiry, any CVC.
3. The webhook marks the session complete — click **Refresh** to see it.
   (No webhook running? **Sync from Stripe** polls the API instead.)

## Files

- `streamlit_app.py` — UI: product setup, checkout session creation, status table
- `webhook_server.py` — Flask receiver for `checkout.session.completed`
- `store.py` — shared SQLite persistence for Stripe IDs (imported, not run directly)
- `requirements.txt` — Python dependencies
- `.env` — Stripe keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`); not committed
- `stripe_store.db` — SQLite database, created automatically on first run
