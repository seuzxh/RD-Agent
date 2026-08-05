"""
Artifact-based Streamlit frontend for the quant research workflow.

5-Tab layout:
1. Strategy Dashboard — global overview, metrics trend, progress
2. Alpha Lab — factor library with lifecycle management
3. Model Lab — model registry with comparison
4. Live Lab — real-time experiment monitoring, history
5. Report — structured metrics summary, charts, download

Usage:
    streamlit run rdagent/log/ui/artifact_app.py -- --log_dir <path>
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit import session_state as state

from rdagent.core.proposal import HypothesisFeedback
from rdagent.log.base import Message
from rdagent.log.storage import FileStorage
from rdagent.log.ui.pages.components import (
    render_alpha_lab,
    render_live_lab,
    render_model_lab,
    render_report,
    render_strategy_dashboard,
)
from rdagent.core.scenario import Scenario

QLIB_SELECTED_METRICS = [
    "IC",
    "1day.excess_return_with_cost.annualized_return",
    "1day.excess_return_with_cost.information_ratio",
    "1day.excess_return_with_cost.max_drawdown",
]


def filter_log_folders(main_log_path):
    folders = [f.relative_to(main_log_path) for f in main_log_path.iterdir() if f.is_dir()]
    return sorted(folders, key=lambda x: x.name)


def should_display(msg: Message) -> bool:
    excluded_tags = st.session_state.get("excluded_tags", [])
    excluded_types = st.session_state.get("excluded_types", [])
    for t in excluded_tags + ["debug_tpl", "debug_llm"]:
        if t in msg.tag.split("."):
            return False
    if type(msg.content).__name__ in excluded_types:
        return False
    return True

st.set_page_config(layout="wide", page_title="RD-Agent - Artifact View", page_icon="🎓", initial_sidebar_state="expanded")

# ── Parse args ──
parser = argparse.ArgumentParser(description="RD-Agent Artifact Streamlit App")
parser.add_argument("--log_dir", type=str, help="Path to the log directory")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

if args.log_dir:
    main_log_path = Path(args.log_dir)
    if not main_log_path.exists():
        st.error(f"Log dir `{main_log_path}` does not exist!")
        st.stop()
else:
    main_log_path = None

# ── Session state ──
if "log_path" not in state:
    if main_log_path:
        folders = filter_log_folders(main_log_path)
        state.log_path = folders[0] if folders else None
    else:
        state.log_path = None

for key, default_val in [
    ("scenario", None), ("fs", None), ("msgs", lambda: defaultdict(lambda: defaultdict(list))),
    ("last_msg", None), ("current_tags", None), ("lround", 0),
    ("erounds", lambda: defaultdict(int)), ("e_decisions", lambda: defaultdict(lambda: defaultdict(tuple))),
    ("hypotheses", lambda: defaultdict(None)), ("h_decisions", lambda: defaultdict(bool)),
    ("metric_series", []), ("all_metric_series", []), ("alpha_baseline_metrics", None),
]:
    if key not in state:
        state[key] = default_val() if callable(default_val) else default_val

if "excluded_tags" not in state:
    state.excluded_tags = ["llm_messages"]
if "excluded_types" not in state:
    state.excluded_types = ["str"]


# ── Log loading ──
def load_logs():
    if state.log_path is None:
        return
    log_path = main_log_path / state.log_path if main_log_path else state.log_path

    # Detect scenario (optional; tabs render without it)
    try:
        for msg in FileStorage(log_path).iter_msg():
            if isinstance(msg.content, Scenario):
                state.scenario = msg.content
                break
    except Exception:
        pass

    # Reset
    state.msgs = defaultdict(lambda: defaultdict(list))
    state.lround = 0
    state.erounds = defaultdict(int)
    state.e_decisions = defaultdict(lambda: defaultdict(tuple))
    state.hypotheses = defaultdict(None)
    state.h_decisions = defaultdict(bool)
    state.metric_series = []
    state.all_metric_series = []
    state.alpha_baseline_metrics = None

    # Load all messages
    try:
        for msg in FileStorage(log_path).iter_msg():
            if not should_display(msg):
                continue
            tag = msg.tag
            # Normalize tags
            tag = re.sub(r"\.evo_loop_\d+", "", tag)
            tag = re.sub(r"Loop_\d+\.[^.]+", "", tag)
            tag = re.sub(r"\.\.", ".", tag)
            tag = re.sub(r"init\.", "", tag)
            tag = re.sub(r"r\.", "", tag)
            tag = re.sub(r"d\.", "", tag)
            tag = re.sub(r"ef\.", "", tag)
            tag = tag.strip(".")

            msg.tag = tag

            if "hypothesis generation" in tag:
                state.lround += 1
                state.hypotheses[state.lround] = msg.content

            state.msgs[state.lround][tag].append(msg)

            # Track metrics for summary
            if "runner result" in tag:
                exp = msg.content
                if exp is not None and hasattr(exp, 'result') and exp.result is not None:
                    sms = exp.result
                    try:
                        sms = sms.loc[QLIB_SELECTED_METRICS] if hasattr(sms, 'loc') else sms
                    except Exception:
                        pass
                    sms.name = f"Round {state.lround}"
                    state.metric_series.append(sms)

            if "feedback" in tag and isinstance(msg.content, HypothesisFeedback):
                state.h_decisions[state.lround] = msg.content.decision
    except Exception:
        pass


# ── Sidebar ──
with st.sidebar:
    st.markdown("# RD-Agent 🤖")
    st.markdown("### Artifact View")

    if main_log_path:
        folders = filter_log_folders(main_log_path)
        selected = st.selectbox("Log Path", folders, index=0, key="log_path_selector")
        if selected != state.log_path:
            state.log_path = selected
            load_logs()
    else:
        st.text_input("Log Path", key="log_path_input", on_change=load_logs)
        if state.log_path:
            load_logs()

    if st.button("🔄 Load Logs", use_container_width=True):
        load_logs()

    if state.scenario:
        st.markdown(f"**Scenario**: {type(state.scenario).__name__}")
    if state.lround > 0:
        st.markdown(f"**Rounds**: {state.lround}")

# ── Main: 5-Tab layout ──
if state.log_path is None:
    st.info("Select a log path to begin.")
    st.stop()

load_logs()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Strategy Dashboard",
    "🔬 Alpha Lab",
    "🤖 Model Lab",
    "⚡ Live Lab",
    "📋 Report",
])

with tab1:
    render_strategy_dashboard()

with tab2:
    render_alpha_lab()

with tab3:
    render_model_lab()

with tab4:
    render_live_lab()

with tab5:
    render_report()