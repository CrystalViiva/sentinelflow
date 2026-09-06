from pathlib import Path

import streamlit as st


STYLESHEET_PATH = Path(__file__).with_name(
    "styles.css"
)


def load_styles() -> None:
    """Load the dashboard's trusted static stylesheet."""
    stylesheet = STYLESHEET_PATH.read_text(
        encoding="utf-8"
    )

    st.markdown(
        f"<style>{stylesheet}</style>",
        unsafe_allow_html=True,
    )


def render_brand_header() -> None:
    """Render SentinelFlow's Agent OS identity and workflow."""
    st.markdown(
        '<div class="sf-badge">'
        "Built for Binance Agent OS"
        "</div>",
        unsafe_allow_html=True,
    )

    st.title("🛡️ SentinelFlow")

    st.caption(
        "Explainable market surveillance. "
        "Deterministic risk controls. "
        "Human-approved execution."
    )

    st.markdown(
        """
        <div class="sf-workflow">
            <span class="sf-step">ANALYSE</span>
            <span class="sf-arrow">→</span>
            <span class="sf-step">RISK CHECK</span>
            <span class="sf-arrow">→</span>
            <span class="sf-step">HUMAN APPROVAL</span>
            <span class="sf-arrow">→</span>
            <span class="sf-step">BINANCE CONFIRMATION</span>
            <span class="sf-arrow">→</span>
            <span class="sf-step">AUDIT</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_execution_boundary() -> None:
    """Explain that SentinelFlow approval is not execution."""
    st.markdown(
        """
        <div class="sf-boundary">
            <div class="sf-boundary-title">
                Official Binance confirmation boundary
            </div>
            <div class="sf-boundary-text">
                SentinelFlow can analyse, risk-check and
                approve a proposal, but approval does not
                execute an order. Authenticated execution
                remains with Binance's official supported
                connector and its final user confirmation.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_engineering_controls() -> None:
    """Render a concise view of backend and security controls."""
    st.divider()
    st.subheader("Backend and security architecture")

    with st.expander(
        "View engineering controls",
        expanded=False,
    ):
        backend, security = st.columns(2)

        with backend:
            st.markdown("#### Backend")
            st.markdown(
                """
                - FastAPI and generated OpenAPI documentation
                - PostgreSQL persistence
                - SQLAlchemy repository layer
                - Alembic schema migrations
                - Pydantic input validation
                - Explicit proposal state machine
                - Optimistic proposal version checks
                - Database row locking
                - Idempotent request identifiers
                - Atomic execution reservation
                """
            )

        with security:
            st.markdown("#### Security")
            st.markdown(
                """
                - Replay and live-source separation
                - Live timestamp freshness validation
                - Binance exchange-rule validation
                - Runtime secret redaction
                - Human approval before reservation
                - Duplicate-attempt protection
                - Unknown-outcome reconciliation
                - No Binance credentials stored
                - Live execution disabled by default
                - Official Binance confirmation preserved
                """
            )

        st.markdown(
            """
            <div class="sf-architecture-note">
                Read-only analysis tools are exposed
                separately from proposal and control tools,
                so analysis capability does not automatically
                imply execution capability.
            </div>
            """,
            unsafe_allow_html=True,
        )