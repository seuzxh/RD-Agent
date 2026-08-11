from pathlib import Path
from typing import Optional

from rdagent.log.sota_query import load_strategy
from rdagent.log.ui.conf import UI_SETTING
from rdagent.scenarios.qlib.domain import Strategy


def load_parent_strategy(strategy_id: str) -> Optional[Strategy]:
    """Load a parent strategy's domain object from its trace path.

    ``strategy_id`` has the form ``<scenario>/<trace_name>`` (e.g.
    ``Finance Data Building/xxx``). The trace path is
    ``Path(UI_SETTING.trace_folder) / strategy_id``, which contains the
    ``__session__/`` used by ``load_strategy``.

    Returns ``None`` (rather than raising) when the trace is missing or cannot
    be loaded — callers fall back to the default ALPHA20 baseline.
    """
    trace_path = Path(UI_SETTING.trace_folder) / strategy_id
    data = load_strategy(trace_path)
    if not data or "error" in data:
        return None
    return Strategy.from_dict(data)