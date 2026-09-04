import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.analytics.features import calculate_features
from app.analytics.scoring import score_accumulation
from app.config import AppMode, get_settings
from app.database.session import SessionLocal
from app.llm.client import explain_signal
from app.replay.loader import load_replay
from app.services.proposals import create_and_evaluate, decide
from app.services.scanner import analyze_and_save

settings = get_settings()
st.set_page_config(page_title="SentinelFlow", page_icon="🛡️", layout="wide")
st.title("🛡️ SentinelFlow")
st.caption(
    "Explainable market surveillance. Deterministic risk controls. Human-approved execution."
)

mode_color = {AppMode.REPLAY: "blue", AppMode.PAPER: "orange", AppMode.LIVE: "red"}[
    settings.app_mode
]
st.markdown(f"**Mode:** :{mode_color}[{settings.app_mode.value.upper()}]")
if settings.app_mode == AppMode.REPLAY:
    st.info("HISTORICAL REPLAY — LIVE EXECUTION DISABLED")

datasets = sorted(Path("data/replay_samples").glob("*.json"))
if not datasets:
    st.error("No replay datasets found.")
    st.stop()

selected = st.sidebar.selectbox(
    "Replay dataset", datasets, format_func=lambda path: path.stem.replace("_", " ").title()
)
events = load_replay(selected)
features = calculate_features(events)
score = score_accumulation(features)

frame = pd.DataFrame(
    [
        {
            "time": item.event_time,
            "open": float(item.open),
            "high": float(item.high),
            "low": float(item.low),
            "close": float(item.close),
            "volume": float(item.volume),
        }
        for item in events
    ]
)
chart = go.Figure(
    data=[
        go.Candlestick(
            x=frame.time, open=frame.open, high=frame.high, low=frame.low, close=frame.close
        )
    ]
)
chart.update_layout(
    height=380, xaxis_rangeslider_visible=False, margin={"l": 10, "r": 10, "t": 30, "b": 10}
)
st.plotly_chart(chart, use_container_width=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Accumulation score", f"{score.score}/100")
c2.metric("Relative volume", f"{features.relative_volume:.2f}×")
c3.metric("Bid/ask depth", f"{features.bid_ask_ratio:.2f}")
c4.metric("Spread", f"{features.spread_percent:.3f}%")
st.subheader(score.classification.replace("_", " ").title())
for evidence in score.supporting_evidence:
    st.success(evidence)
for evidence in score.counter_evidence:
    st.warning(evidence)

if st.button("Save replay signal", type="primary"):
    with SessionLocal() as db:
        signal = analyze_and_save(db, events, "replay")
        st.session_state.signal_id = str(signal.id)
    st.success(f"Signal saved: {st.session_state.signal_id}")

with st.expander("AI explanation"):
    if st.button("Generate explanation"):
        st.write(
            explain_signal(
                features.symbol,
                {"features": features.model_dump(mode="json"), "score": score.model_dump()},
                score.counter_evidence,
            )
        )

st.divider()
st.subheader("Paper proposal and Risk Gate")
if "signal_id" not in st.session_state:
    st.caption("Save the replay signal before creating a proposal.")
else:
    if "proposal_request_id" not in st.session_state:
        st.session_state.proposal_request_id = str(uuid.uuid4())
    amount = st.number_input("Proposed Spot purchase (USDT)", min_value=1.0, value=10.0, step=1.0)
    if st.button("Create and check proposal"):
        from app.database.models import Signal

        with SessionLocal() as db:
            signal = db.get(Signal, uuid.UUID(st.session_state.signal_id))
            proposal, risk = create_and_evaluate(
                db,
                settings,
                signal,
                Decimal(str(amount)),
                Decimal(5),
                Decimal(100),
                uuid.UUID(st.session_state.proposal_request_id),
            )
            st.session_state.proposal_id = str(proposal.id)
            st.session_state.proposal_version = proposal.version
            st.session_state.risk = risk.model_dump()
        st.rerun()

if "risk" in st.session_state:
    risk = st.session_state.risk
    st.markdown(f"**Risk Gate:** {'PASSED' if risk['passed'] else 'BLOCKED'}")
    with st.expander("All checks", expanded=not risk["passed"]):
        for item in risk["checks"]:
            st.write(
                ("✅" if item["passed"] else "❌"), item["name"], item["observed"], item["required"]
            )
    acknowledged = st.checkbox("I reviewed the symbol, side and amount.")
    left, right = st.columns(2)
    if left.button("Approve proposal", disabled=not risk["passed"] or not acknowledged):
        with SessionLocal() as db:
            result = decide(
                db, st.session_state.proposal_id, st.session_state.proposal_version, True
            )
        st.success(
            f"Proposal {result.status}. Binance execution still requires separate MCP confirmation."
        )
    if right.button("Reject proposal"):
        with SessionLocal() as db:
            result = decide(
                db, st.session_state.proposal_id, st.session_state.proposal_version, False
            )
        st.warning(f"Proposal {result.status}.")
