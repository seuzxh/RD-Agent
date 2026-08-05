"""
Page components for the artifact-based frontend.

Each function renders a Streamlit page section.
"""

from __future__ import annotations

import textwrap
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from rdagent.components.coder.factor_coder.factor import FactorTask
from rdagent.components.coder.model_coder.model import ModelTask
from rdagent.core.proposal import Hypothesis, HypothesisFeedback
from rdagent.log.ui.pages import (
    extract_backtest_charts,
    extract_factors,
    extract_hypotheses,
    extract_metrics_trend,
    extract_models,
    get_factor_code,
    get_model_code,
)
from rdagent.log.ui.qlib_report_figure import report_figure


# ──────────────────────────────────────────────
# Strategy Dashboard
# ──────────────────────────────────────────────


def render_strategy_dashboard():
    """Strategy overview: description, progress bar, metrics trend chart."""
    st.header("Strategy Dashboard", anchor="_strategy")

    # Description
    rounds = extract_hypotheses()
    st.markdown(f"**Total Rounds**: {len(rounds)}")

    # Progress
    if rounds:
        progress = min(len(rounds) / 20, 1.0)
        st.progress(progress, text=f"{len(rounds)} / 20 rounds")

    # Metrics trend
    trend = extract_metrics_trend()
    if not trend.empty:
        st.subheader("Metrics Trend")
        cols = ["IC", "Annualized Return", "Information Ratio", "Max Drawdown"]
        available = [c for c in cols if c in trend.columns]
        if len(available) == 1:
            fig = px.line(trend, y=available[0], markers=True)
            st.plotly_chart(fig, use_container_width=True)
        elif len(available) > 1:
            fig = make_subplots(rows=1, cols=len(available), subplot_titles=available)
            for i, col in enumerate(available):
                fig.add_trace(
                    go.Scatter(x=trend.index, y=trend[col], mode="lines+markers", name=col),
                    row=1, col=i + 1,
                )
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)

    # Hypothesis summary
    st.subheader("Hypotheses")
    for item in reversed(rounds[-10:]):  # last 10
        h = item["hypothesis"]
        if h is None:
            continue
        decision = item["decision"]
        icon = "✅" if decision else "❌"
        st.markdown(f"{icon} **Round {item['round']}**: {h.hypothesis}")
        if h.concise_reason:
            st.caption(f"_{h.concise_reason}_")


# ──────────────────────────────────────────────
# Alpha Lab
# ──────────────────────────────────────────────


def render_alpha_lab():
    """Factor library: list, filter, search, detail expansion."""
    st.header("Alpha Lab", anchor="_alpha_lab")

    pool = extract_factors()
    all_factors = pool.all

    if not all_factors:
        st.info("No factors discovered yet. Run a factor mining session first.")
        return

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Status", ["All", "sota", "active", "deprecated", "pending"],
        )
    with col2:
        search = st.text_input("Search", placeholder="Factor name...")
    with col3:
        sort_by = st.selectbox("Sort by", ["IC", "ICIR", "Round", "Name"])

    # Filter
    filtered = all_factors
    if status_filter != "All":
        filtered = [f for f in filtered if f.status.value == status_filter]
    if search:
        filtered = [f for f in filtered if search.lower() in f.name.lower()]

    # Sort
    if sort_by == "IC":
        filtered.sort(key=lambda f: f.factor_metrics.ic if f.factor_metrics else 0, reverse=True)
    elif sort_by == "ICIR":
        filtered.sort(key=lambda f: f.factor_metrics.icir if f.factor_metrics else 0, reverse=True)
    elif sort_by == "Round":
        filtered.sort(key=lambda f: f.round_number, reverse=True)
    else:
        filtered.sort(key=lambda f: f.name)

    # Summary
    st.markdown(f"**{len(filtered)}** factors (of {len(all_factors)} total)")

    # Table
    for factor in filtered:
        status_icon = {
            "sota": "✅ SOTA",
            "active": "📌 Active",
            "deprecated": "❌ Deprecated",
            "pending": "⏳ Pending",
        }.get(factor.status.value, factor.status.value)

        with st.expander(f"**{factor.name}** — {status_icon}  (Round {factor.round_number})"):
            cols = st.columns([1, 1, 1, 1])
            if factor.factor_metrics:
                cols[0].metric("IC", f"{factor.factor_metrics.ic:.4f}")
                cols[1].metric("ICIR", f"{factor.factor_metrics.icir:.4f}")
                cols[2].metric("Rank IC", f"{factor.factor_metrics.rank_ic:.4f}")
                cols[3].metric("Rank ICIR", f"{factor.factor_metrics.rank_icir:.4f}")
            else:
                cols[0].metric("IC", "N/A")

            if factor.formulation:
                st.markdown(f"**Formulation**: ${factor.formulation}$")
            if factor.description:
                st.markdown(f"**Description**: {factor.description}")

            # Show code
            code = get_factor_code(factor.round_number, factor.name)
            if code:
                with st.expander("View Code"):
                    st.code(code, language="python")

            # Show backtest chart
            charts = extract_backtest_charts(factor.round_number)
            if charts:
                fig = report_figure(charts["ret"], charts.get("group"))
                st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────
# Model Lab
# ──────────────────────────────────────────────


def render_model_lab():
    """Model registry: list, compare, detail expansion."""
    st.header("Model Lab", anchor="_model_lab")

    models = extract_models()

    if not models:
        st.info("No models trained yet. Run a model training session first.")
        return

    # Summary table
    st.markdown(f"**{len(models)}** models trained")

    df = pd.DataFrame(models)
    display_cols = ["name", "type", "round", "status", "annualized_return", "max_drawdown", "information_ratio"]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols], use_container_width=True, hide_index=True)

    # Detail for each model
    for model in models:
        status_icon = "✅ SOTA" if model["status"] == "SOTA" else "📌 Active"
        with st.expander(f"**{model['name']}** — {status_icon}  (Round {model['round']})"):
            cols = st.columns(4)
            cols[0].metric("Annualized Return", f"{model['annualized_return']:.2%}")
            cols[1].metric("Max Drawdown", f"{model['max_drawdown']:.2%}")
            cols[2].metric("Information Ratio", f"{model.get('information_ratio', 0):.4f}")
            cols[3].metric("Calmar Ratio", f"{model.get('calmar_ratio', 0):.4f}")

            if model.get("features"):
                st.markdown(f"**Features**: {', '.join(model['features'])}")

            # Show code
            code = get_model_code(model["round"])
            if code:
                with st.expander("View Code"):
                    st.code(code, language="python")

            # Show backtest chart
            charts = extract_backtest_charts(model["round"])
            if charts:
                fig = report_figure(charts["ret"], charts.get("group"))
                st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────
# Live Lab
# ──────────────────────────────────────────────


def render_live_lab():
    """Real-time experiment monitoring and experiment history."""
    st.header("Live Lab", anchor="_live_lab")

    rounds = extract_hypotheses()
    if not rounds:
        st.info("No experiment data available. Load a log file to view.")
        return

    # Experiment history
    st.subheader("Experiment History")
    for item in reversed(rounds):
        h = item["hypothesis"]
        fb = item["feedback"]
        decision = item["decision"]
        icon = "✅" if decision else "❌"

        with st.expander(f"Round {item['round']} {icon}"):
            if h:
                st.markdown(f"**Hypothesis**: {h.hypothesis}")
                if h.reason:
                    st.markdown(f"**Reason**: {h.reason}")
            if fb:
                st.markdown(f"**Observations**: {fb.observations}")
                st.markdown(f"**Decision**: {'Accepted' if fb.decision else 'Rejected'}")
                if fb.reason:
                    st.markdown(f"**Reason**: {fb.reason}")

            # Show backtest chart
            charts = extract_backtest_charts(item["round"])
            if charts:
                fig = report_figure(charts["ret"], charts.get("group"))
                st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────


def render_report():
    """Full report: metrics summary, return charts, trend."""
    st.header("Research Report", anchor="_report")

    trend = extract_metrics_trend()
    if trend.empty:
        st.info("No data available for report generation.")
        return

    # Key metrics summary
    st.subheader("Key Metrics")
    latest = trend.iloc[-1] if not trend.empty else {}
    cols = st.columns(5)
    metrics_display = [
        ("IC", latest.get("IC", 0), "{:.4f}"),
        ("ICIR", latest.get("ICIR", 0), "{:.4f}"),
        ("Ann. Return", latest.get("Annualized Return", 0), "{:.2%}"),
        ("Max DD", latest.get("Max Drawdown", 0), "{:.2%}"),
        ("Info. Ratio", latest.get("Information Ratio", 0), "{:.4f}"),
    ]
    for i, (label, val, fmt) in enumerate(metrics_display):
        cols[i].metric(label, fmt.format(val) if val else "N/A")

    # Return chart
    st.subheader("Returns")
    # Try to get the latest round's backtest chart
    rounds = getattr(st.session_state, "msgs", {})
    max_round = max(rounds.keys()) if rounds else 0
    charts = extract_backtest_charts(max_round) if max_round > 0 else None
    if charts:
        fig = report_figure(charts["ret"], charts.get("group"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Backtest chart not available.")

    # Metrics trend
    st.subheader("Metrics Trend")
    plot_cols = ["IC", "ICIR", "Annualized Return", "Information Ratio"]
    available = [c for c in plot_cols if c in trend.columns]
    if len(available) >= 1:
        fig = px.line(trend[available], markers=True)
        st.plotly_chart(fig, use_container_width=True)

    # Download
    csv = trend.to_csv()
    st.download_button("Download Metrics (CSV)", data=csv, file_name="metrics.csv", mime="text/csv")