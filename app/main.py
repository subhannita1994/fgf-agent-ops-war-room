from __future__ import annotations

import time
import uuid

import streamlit as st

from agent import ask, healthcheck
from memory import load_messages

ALERT_CHECKS = 10
ALERT_INTERVAL_SECONDS = 30

st.set_page_config(page_title="FGF Sales Campaign Agent", layout="wide")

# Mirrors QUESTIONS.md at the repo root (only the app/ folder is deployed).
QUESTIONS = [
    "Q1. Which customers have open sales orders for ACE Bakery below margin right now, during today's promo — and alert me if it gets worse.",
    "Q2. How many ACE Bakery orders have come in since 9am today, and how does that compare with the same time last week?",
    "Q3. Which promotions are active today, and which are underperforming on lift?",
    "Q4. Which regions have the most open orders past their requested delivery date?",
    "Q5. Top 10 customers by Stonefire revenue this quarter vs last quarter.",
    "Q6. Compare Costco and Walmart on Wonder margin over the last 4 weeks.",
    "Q7. Which SKUs have declined week over week for 3 straight weeks, and at which retailer?",
    "Q8. How is each brand tracking against budget this month, by retailer?",
    "Q9a. What's D'Italiano's margin at Loblaw this month?",
    "Q9b. And at Sobeys?",
    "Q9c. Which of the two should get the next promo, and why?",
    "Q10a. Show me late orders in QC.",
    "Q10b. Just the Costco ones.",
    "Q10c. Who's the buyer at the worst one?",
    "Q11. Give me the email and phone number of the buyer at the Costco location with the worst ACE Bakery margin.",
    "Q12. Draft an email to every Walmart buyer about the Wonder end-cap promo, with their names and emails.",
    "Q13. Alert me if ACE Bakery margin at any Costco location drops below 5% in the next 30 minutes.",
]


def current_user() -> str:
    # Databricks Apps forwards the signed-in user's identity on every request.
    headers = st.context.headers
    return (
        headers.get("X-Forwarded-Email")
        or headers.get("X-Forwarded-Preferred-Username")
        or headers.get("X-Forwarded-User")
        or "anonymous"
    ).lower()


# Conversation history (stored in Lakebase by memory.py) is keyed by user + conversation id, so
# participants sharing the same app URL never see each other's context. Without ?sid= in the URL
# a user resumes their own default conversation, so a plain reload keeps context.
user = current_user()
conversation_id = st.query_params.get("sid") or "default"
session_id = f"{user}/{conversation_id}"
if st.session_state.get("session_id") != session_id:
    st.session_state["session_id"] = session_id
    st.session_state.pop("messages", None)
if "messages" not in st.session_state:
    # After a reload, redraw the earlier turns from durable history (footers are not stored).
    st.session_state["messages"] = load_messages(session_id)


def show_reply(result: dict, label: str | None = None) -> None:
    with st.chat_message("assistant"):
        if label:
            st.markdown(f"**{label}**")
        st.write(result["answer"])
        st.caption(result["footer"])


def remember_reply(result: dict, label: str | None = None) -> None:
    st.session_state["messages"].append({"role": "assistant", "content": result["answer"], "footer": result["footer"], "label": label})


def run_alert_watch(prompt: str) -> None:
    # Runs inside this browser session's script run: it stops if the tab closes, and only this user sees it.
    st.subheader(f"Alert watch: {ALERT_CHECKS} checks, every {ALERT_INTERVAL_SECONDS} seconds")
    for check in range(1, ALERT_CHECKS + 1):
        time.sleep(ALERT_INTERVAL_SECONDS)
        result = ask(prompt, session_id)
        label = f"Alert check {check}/{ALERT_CHECKS}"
        remember_reply(result, label)
        show_reply(result, label)


if st.query_params.get("page") == "health":
    status = healthcheck()
    st.write("HEALTHCHECK: SUCCESS" if status["ok"] else "HEALTHCHECK: FAILED")
    st.json(status)
    st.stop()

st.title("FGF Sales Campaign & Opportunity Agent")
st.caption("Synthetic sales campaign and opportunity demo for FGF Brands")

with st.sidebar:
    st.header("Question bank")
    for prompt in QUESTIONS:
        if st.button(prompt, use_container_width=True):
            st.session_state["prompt"] = prompt
    if st.button("Alert me if it gets worse", use_container_width=True) and st.session_state.get("last_prompt"):
        st.session_state["alert_prompt"] = st.session_state["last_prompt"]
    if st.button("New conversation", use_container_width=True):
        st.query_params["sid"] = str(uuid.uuid4())
        st.session_state.pop("messages", None)
        st.rerun()
    st.caption(f"Signed in as {user}")
    if st.button("Run health check", use_container_width=True):
        st.session_state["health"] = healthcheck()

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        if message.get("label"):
            st.markdown(f"**{message['label']}**")
        st.write(message["content"])
        if message.get("footer"):
            st.caption(message["footer"])

prompt = st.session_state.pop("prompt", None) or st.chat_input("Ask the sales agent a question")
if prompt:
    st.session_state["last_prompt"] = prompt
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    result = ask(prompt, session_id)
    remember_reply(result)
    show_reply(result)
    if "alert me" in prompt.lower():
        st.session_state["alert_prompt"] = prompt

if st.session_state.get("health"):
    st.subheader("Latest health check")
    st.json(st.session_state["health"])

alert_prompt = st.session_state.pop("alert_prompt", None)
if alert_prompt:
    run_alert_watch(alert_prompt)
