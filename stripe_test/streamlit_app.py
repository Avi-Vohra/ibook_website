"""Streamlit UI for accepting a one-time payment with Stripe Checkout.

Run the webhook receiver separately (webhook_server.py) so
checkout.session.completed events get recorded in the shared SQLite store.
"""

import os

import stripe
import streamlit as st
from dotenv import load_dotenv

import store

load_dotenv()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

PRODUCT_NAME = "Example Product"
PRODUCT_CURRENCY = "usd"
PRODUCT_UNIT_AMOUNT = 2000  # $20.00

SUCCESS_URL = (
    "https://dashboard.stripe.com/workbench/blueprints/one-time-payment/"
    "checkout-chapter?confirmation-redirect=create-checkout-session"
)
CANCEL_URL = SUCCESS_URL

st.set_page_config(page_title="Stripe Checkout Demo", page_icon="💳")
st.title("💳 One-time payment with Stripe Checkout")

if not stripe.api_key:
    st.error("STRIPE_SECRET_KEY is not set. Copy .env.example to .env and add your keys "
             "from https://dashboard.stripe.com/apikeys, then restart.")
    st.stop()


def ensure_product():
    product = store.get_product(PRODUCT_NAME)
    if product:
        return product
    stripe_product = stripe.Product.create(
        name=PRODUCT_NAME,
        default_price_data={
            "currency": PRODUCT_CURRENCY,
            "unit_amount": PRODUCT_UNIT_AMOUNT,
        },
    )
    store.save_product(
        PRODUCT_NAME,
        stripe_product.id,
        stripe_product.default_price,
        PRODUCT_CURRENCY,
        PRODUCT_UNIT_AMOUNT,
    )
    return store.get_product(PRODUCT_NAME)


st.header("1 · Product & pricing")
product = store.get_product(PRODUCT_NAME)
if product:
    st.success(f"**{product['name']}** — ${product['unit_amount'] / 100:.2f} "
               f"{product['currency'].upper()}")
    st.caption(f"product: `{product['stripe_product_id']}` · price: `{product['stripe_price_id']}`")
else:
    st.info("No product yet — it will be created in Stripe on first use.")
    if st.button("Create product in Stripe"):
        with st.spinner("Creating product..."):
            ensure_product()
        st.rerun()

st.header("2 · Checkout")
if st.button("Create Checkout Session", type="primary"):
    with st.spinner("Creating Checkout Session..."):
        p = ensure_product()
        session = stripe.checkout.Session.create(
            line_items=[{"price": p["stripe_price_id"], "quantity": 1}],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
        )
        store.save_checkout_session(session.id, p["stripe_price_id"], session.url)
        st.session_state["last_session"] = {"id": session.id, "url": session.url}

if last := st.session_state.get("last_session"):
    st.success(f"Session `{last['id']}` created.")
    st.link_button("Open Stripe Checkout →", last["url"])
    st.caption("Pay with test card 4242 4242 4242 4242, any future expiry, any CVC.")

st.header("3 · Payment status")
st.caption("Completed sessions are recorded by the webhook receiver "
           "(`python webhook_server.py` + `stripe listen --forward-to localhost:4242/webhook`). "
           "“Sync from Stripe” polls the API directly as a fallback.")

col1, col2 = st.columns(2)
if col1.button("Refresh"):
    st.rerun()
if col2.button("Sync from Stripe"):
    with st.spinner("Checking session status with Stripe..."):
        for row in store.list_checkout_sessions():
            if row["status"] != "complete":
                s = stripe.checkout.Session.retrieve(row["stripe_session_id"])
                if s.status == "complete":
                    email = getattr(s.customer_details, "email", None)
                    store.mark_session_completed(
                        s.id, s.payment_status, s.amount_total, s.currency, email,
                    )
    st.rerun()

sessions = store.list_checkout_sessions()
if sessions:
    st.dataframe(
        [
            {
                "session": s["stripe_session_id"],
                "status": s["status"],
                "payment": s["payment_status"] or "—",
                "amount": f"${s['amount_total'] / 100:.2f}" if s["amount_total"] else "—",
                "email": s["customer_email"] or "—",
                "created": s["created_at"],
                "completed": s["completed_at"] or "—",
            }
            for s in sessions
        ],
        use_container_width=True,
    )
else:
    st.info("No checkout sessions yet.")
