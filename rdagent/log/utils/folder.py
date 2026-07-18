"""
This module provides some useful functions for working with logger folders.
"""

import pickle
from pathlib import Path

import pandas as pd

from rdagent.utils.workflow import LoopBase


def get_first_session_file_after_duration(log_folder: str | Path, duration: str | pd.Timedelta) -> Path:
    log_folder = Path(log_folder)
    duration_dt = pd.Timedelta(duration)
    # iterate the dump steps in increasing order
    files = sorted(
        (log_folder / "__session__").glob("*/*_*"), key=lambda f: (int(f.parent.name), int(f.name.split("_")[0]))
    )
    fp = None
    for fp in files:
        with fp.open("rb") as f:
            session_obj: LoopBase = pickle.load(f)
        timer = session_obj.timer
        all_duration = timer.all_duration
        remain_time_duration = timer.remain_time()
        if all_duration is None or remain_time_duration is None:
            msg = "Timer is not configured"
            raise ValueError(msg)
        time_spent = all_duration - remain_time_duration
        if time_spent >= duration_dt:
            break
    if fp is None:
        msg = f"No session file found after duration {duration}"
        raise ValueError(msg)
    return fp
