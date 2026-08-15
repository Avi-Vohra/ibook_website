"""Minimal webhook receiver for checkout.session.completed.

Streamlit can't accept webhook POSTs, so this small Flask server writes
completed payments into the shared SQLite store that the Streamlit app reads.

Run alongside the Streamlit app:
    python webhook_server.py
    stripe listen --forward-to localhost:4242/webhook
"""

import os

import stripe
from dotenv import load_dotenv
from flask import Flask, jsonify, request

import store

load_dotenv()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

app = Flask(__name__)


@app.post("/webhook")
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            return jsonify({"error": "invalid webhook payload or signature"}), 400
    else:
        # No secret configured (local experimentation only) — trust the payload.
        event = stripe.Event.construct_from(request.get_json(force=True), stripe.api_key)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        details = session.get("customer_details") or {}
        store.mark_session_completed(
            session["id"],
            session.get("payment_status"),
            session.get("amount_total"),
            session.get("currency"),
            details.get("email"),
        )
        app.logger.info("Checkout session %s completed", session["id"])

    return jsonify({"received": True})


if __name__ == "__main__":
    app.run(port=4242)
