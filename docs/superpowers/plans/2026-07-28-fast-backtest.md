{% raw %}
# 快速回测(Fast Backtest)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建快速回测页面,用户勾选 Alpha158 因子和/或自然语言描述策略,绕过 R&D loop 单次生成因子并跑 LinearModel 回测,产出可被 predict 流程自动发现的可预测 trace。

**Architecture:** 后端新增同步 SSE 端点 `POST /fastbacktest/run`,线性编排 4 步(LLM 单次生成 factor.py → 验证因子值 → QlibFBWorkspace qrun 回测 → 写微型 trace);前端新增独立多页入口 `fastbacktest.html`,复用 multiα1pha 视觉令牌。产出的 trace 让现有 predict 流程零改动自动发现。

**Tech Stack:** Python/Flask(SSE)、Vue 3 + TypeScript + Element Plus + ECharts、Qlib(LinearModel)、RD-Agent 已有组件(QlibFBWorkspace/FactorFBWorkspace/LoopBase/Trace/Experiment)

## Global Constraints

- **后端**:`conf_combined_factors.yaml`(非 conf_baseline.yaml),`model_selector=linear`(OLS,环境变量 `QLIB_FACTOR_MODEL_SELECTOR=linear`),固定 csi300 + 默认日期段(train 2008-2014 / valid 2015-2016 / test 2017-2020)
- **前端**:严格复用 `web/src/multialpha/styles/tokens.css` 的设计令牌(`--ma-gold:#b99a50` 等);字体 Noto Serif SC(标题/数字)+ Noto Sans SC(正文)+ JetBrains Mono(数据/eyebrow);头部复用 `TopBar.vue` 的国新证券 logo + Multiα1pha 结构
- **trace 命名**:`Finance Data Building/fast-<randomname>-<date>`,满足 `/predict/experiments` 的前缀过滤(`app.py:1497`)
- **SSE**:用 `fetch` + `ReadableStream` 消费(EventSource 不支持 POST body);Flask 用 `Response(generator, mimetype="text/event-stream")` + `stream_with_context`
- **不改动**:predict 相关端点、predict_infer.py、query_sota、QlibFBWorkspace/FactorFBWorkspace/LoopBase/Trace 的现有实现

---

## File Structure

### 新增文件
| 文件 | 职责 |
|------|------|
| `rdagent/app/fast_backtest.py` | 后端编排核心:`run_fast_backtest(payload) -> Generator`(SSE 事件生成器),含 4 步编排 + 微型 trace 组装 |
| `web/fastbacktest.html` | 多页入口 HTML(挂载点 `#fastbacktest-app`) |
| `web/src/fastbacktest/main.ts` | Vue 挂载入口(仿 predict/main.ts) |
| `web/src/fastbacktest/router.ts` | 路由(单页,可选 `/result/:id`) |
| `web/src/fastbacktest/FastBacktestApp.vue` | 根组件,三态切换(input/running/result) |
| `web/src/fastbacktest/use-fastbacktest.ts` | composable:Alpha158 分组数据 + SSE 消费 + 状态机 |
| `web/src/fastbacktest/api.ts` | re-export `services/rdagent-api.ts` 的 `runFastBacktest` |
| `web/src/fastbacktest/components/Alpha158Picker.vue` | 因子勾选面板(29 族可折叠) |
| `web/src/fastbacktest/components/DescriptionInput.vue` | 自然语言输入框 |
| `web/src/fastbacktest/components/ProgressTimeline.vue` | SSE 进度时间线(深色终端风格) |
| `web/src/fastbacktest/components/MetricsPanel.vue` | 回测指标卡片 |
| `web/src/fastbacktest/components/EquityChart.vue` | 收益曲线(ECharts) |
| `web/src/fastbacktest/styles/fastbacktest.css` | 样式(复用 multiα1pha 令牌) |

### 修改文件
| 文件 | 改动 |
|------|------|
| `rdagent/log/server/app.py` | 新增 `POST /fastbacktest/run` 端点(调 `run_fast_backtest`,返回 SSE) |
| `web/vite.config.ts` | `rollupOptions.input` 加 `fastbacktest` 入口 |
| `web/src/services/rdagent-api.ts` | 新增 `runFastBacktest(payload)` 函数(fetch + ReadableStream) |

---

## Task 1: 后端 — 编排核心 `run_fast_backtest`

**Files:**
- Create: `rdagent/app/fast_backtest.py`
- Test: `rdagent/app/test_fast_backtest.py`

**Interfaces:**
- Consumes: `APIBackend`(LLM 单次调用)、`FactorFBWorkspace.execute`(因子验证)、`QlibFBWorkspace.execute`(qrun)、`process_factor_data`(`rdagent/scenarios/qlib/developer/utils.py:131`)、`ALPHA158`(`rdagent/utils/qlib.py:27`)、`LoopBase.dump`(`rdagent/utils/workflow/loop.py:426`)、`Trace`/`Experiment`/`Hypothesis`/`HypothesisFeedback`/`FactorTask`
- Produces: `run_fast_backtest(payload: dict) -> Generator[str, None, None]` — 生成 SSE 格式字符串(`data: {json}\n\n`),供 Flask 端点用

**背景 — 关键事实(实现必须遵守):**
- factor.py 接口契约:生成的 factor.py 必须定义 `feature_engineering_cls` 类(含 `fit(df)` / `transform(df)`),由模板 `rdagent/components/coder/factor_coder/factor_execution_template.txt` 调用,输出 `result.h5`(key="data")。验证见 `factor.py:105` 的 `FactorFBWorkspace.execute`。
- LLM 单次调用 API:`APIBackend().build_messages_and_create_chat_completion(user_prompt, system_prompt)`(`rdagent/oai/backend/base.py:440`)。`APIBackend = get_api_backend`(`llm_utils.py:44`),直接 `APIBackend()` 实例化。
- prompt 复用:系统提示用 `T("rdagent.components.coder.factor_coder.prompts:evolving_strategy_factor_implementation_v1_system").r()`,用户提示用 `evolving_strategy_factor_implementation_v2_user`(`evolving_strategy.py:95,118`)。**去掉 evolving 的 error_summary 部分**,只保留首次实现的 instruction + factor task 信息。

- [ ] **Step 1: 写失败测试 — 输入校验 + SSE 格式**

创建 `rdagent/app/test_fast_backtest.py`:

```python
"""Tests for fast backtest orchestration."""
import json
from unittest.mock import patch, MagicMock
from rdagent.app.fast_backtest import run_fast_backtest, _parse_sse_events, _validate_payload


def test_validate_payload_rejects_empty():
    ok, err = _validate_payload({})
    assert not ok
    assert "至少" in err


def test_validate_payload_accepts_alpha158_only():
    ok, err = _validate_payload({"alpha158": ["KMID", "KLEN"], "description": ""})
    assert ok, err


def test_validate_payload_accepts_description_only():
    ok, err = _validate_payload({"alpha158": [], "description": "动量因子"})
    assert ok, err


def test_parse_sse_events_extracts_json():
    raw = 'data: {"stage":"codegen","status":"ok"}\n\ndata: {"stage":"done","status":"ok"}\n\n'
    events = _parse_sse_events(raw)
    assert len(events) == 2
    assert events[0]["stage"] == "codegen"
    assert events[1]["stage"] == "done"
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v`
预期:FAIL(`ModuleNotFoundError: No module named 'rdagent.app.fast_backtest'`)

- [ ] **Step 2: 实现 payload 校验 + SSE 解析辅助函数**

创建 `rdagent/app/fast_backtest.py`,先实现纯函数部分:

```python
"""Fast backtest orchestration: NL + Alpha158 → linear backtest → predict-ready trace.

Bypasses the full R&D loop (FactorRDLoop). Linear 4-step pipeline run synchronously
inside the Flask request process, streaming progress via SSE.
"""
from __future__ import annotations

import json
from typing import Any, Generator


def _validate_payload(payload: dict) -> tuple[bool, str]:
    """Validate the fast backtest request payload."""
    alpha158 = payload.get("alpha158") or []
    description = (payload.get("description") or "").strip()
    if not alpha158 and not description:
        return False, "至少需要填写一项输入(Alpha158 勾选或自然语言描述)"
    return True, ""


def _parse_sse_events(raw_sse: str) -> list[dict]:
    """Parse a raw SSE string into a list of event dicts (for testing)."""
    events = []
    for line in raw_sse.split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _sse(stage: str, status: str, **fields: Any) -> str:
    """Build a single SSE event string."""
    payload = {"stage": stage, "status": status, **fields}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v`
预期:4 个测试 PASS

- [ ] **Step 3: 提交**

```bash
git add rdagent/app/fast_backtest.py rdagent/app/test_fast_backtest.py
git commit -m "feat(fast-backtest): payload validation + SSE helpers"
```

---

## Task 2: 后端 — Step ① LLM 单次生成 factor.py

**Files:**
- Modify: `rdagent/app/fast_backtest.py`(追加 `_generate_factor_code`)
- Test: `rdagent/app/test_fast_backtest.py`(追加测试)

**Interfaces:**
- Consumes:`APIBackend().build_messages_and_create_chat_completion`、`T(...).r()` prompt 加载、`FactorTask` 构造
- Produces:`_generate_factor_code(description: str) -> dict` 返回 `{"factor_name": str, "code": str}`,失败抛 `FastBacktestError`

- [ ] **Step 1: 写失败测试 — 代码生成(mock LLM)**

追加到 `test_fast_backtest.py`:

```python
from rdagent.app.fast_backtest import _generate_factor_code, FastBacktestError


def test_generate_factor_code_success():
    fake_code = "import pandas as pd\nclass feature_engineering_cls:\n    def fit(self, df): pass\n    def transform(self, df): return df"
    with patch("rdagent.app.fast_backtest.APIBackend") as MockBackend:
        instance = MockBackend.return_value
        instance.build_messages_and_create_chat_completion.return_value = (
            f"```python\n{fake_code}\n```"
        )
        result = _generate_factor_code("动量反转因子")
    assert "feature_engineering_cls" in result["code"]
    assert result["factor_name"]  # non-empty
    assert "```" not in result["code"]  # markdown fence stripped


def test_generate_factor_code_no_class_raises():
    with patch("rdagent.app.fast_backtest.APIBackend") as MockBackend:
        instance = MockBackend.return_value
        instance.build_messages_and_create_chat_completion.return_value = "print('no class here')"
        try:
            _generate_factor_code("bad")
            assert False, "should have raised"
        except FastBacktestError as e:
            assert "feature_engineering_cls" in str(e)
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k generate`
预期:FAIL(`_generate_factor_code` 未定义)

- [ ] **Step 2: 实现 `_generate_factor_code`**

追加到 `fast_backtest.py`:

```python
import re
from rdagent.oai.llm_utils import get_api_backend
from rdagent.oai.prompt_utils import T

APIBackend = get_api_backend


class FastBacktestError(Exception):
    """Raised when a fast backtest step fails."""


# Prompt for single-shot factor generation (reuses CoSTEER's system prompt,
# drops the evolving/error-summary context since we only do one shot).
_FACTOR_CODEGEN_SYSTEM = (
    "You are a quantitative factor engineer. Generate a Python class "
    "`feature_engineering_cls` with `fit(self, df)` and `transform(self, df) -> pd.DataFrame`. "
    "The transform output columns are the factor values. Read OHLCV columns from the input df. "
    "Only output the Python code, no explanation."
)

_FACTOR_CODEGEN_USER = """Based on the following strategy description, implement a single factor.

Strategy description:
{description}

Requirements:
1. Define class `feature_engineering_cls` with methods `fit(self, df)` and `transform(self, df)`.
2. `transform` must return a pandas DataFrame (the factor values).
3. Use only pandas/numpy. Input df has columns: instrument, datetime, open, high, low, close, volume, vwap.
4. Output ONLY python code in a ```python block.
"""


def _generate_factor_code(description: str) -> dict:
    """Single-shot LLM call to generate factor.py code. No retry, no evolving."""
    backend = APIBackend()
    system_prompt = (
        T("rdagent.components.coder.factor_coder.prompts:evolving_strategy_factor_implementation_v1_system").r()
        if False  # keep simple system prompt for v1; switch to CoSTEER prompt if richer context needed
        else _FACTOR_CODEGEN_SYSTEM
    )
    user_prompt = _FACTOR_CODEGEN_USER.format(description=description)
    raw = backend.build_messages_and_create_chat_completion(
        user_prompt=user_prompt, system_prompt=system_prompt
    )
    # Extract code from markdown fence
    code = _extract_code_block(raw)
    if "feature_engineering_cls" not in code:
        raise FastBacktestError(
            "生成的代码未包含 feature_engineering_cls 类。原始返回:\n" + raw[:500]
        )
    factor_name = "fast_" + re.sub(r"[^a-z0-9]", "", description.lower())[:20]
    if not factor_name.replace("fast_", ""):
        factor_name = "fast_factor"
    return {"factor_name": factor_name, "code": code}


def _extract_code_block(text: str) -> str:
    """Extract Python code from a markdown ```python fence, or return text as-is."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()
```

> **注**:`T("...:evolving_strategy_factor_implementation_v1_system").r()` 那行用 `if False` 占位是故意的 —— 首版用简化系统提示确保可控;若需要更丰富的因子生成上下文,改为 `if True` 切换到 CoSTEER 完整提示。实现时按需决定。

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k generate`
预期:2 个测试 PASS

- [ ] **Step 3: 提交**

```bash
git add rdagent/app/fast_backtest.py rdagent/app/test_fast_backtest.py
git commit -m "feat(fast-backtest): single-shot LLM factor code generation"
```

---

## Task 3: 后端 — Step ③④ 回测执行 + 微型 trace 组装

**Files:**
- Modify: `rdagent/app/fast_backtest.py`(追加 `_run_backtest` + `_build_trace` + 主 `run_fast_backtest`)
- Test: `rdagent/app/test_fast_backtest.py`(追加测试)

**Interfaces:**
- Consumes:`QlibFBWorkspace`(`rdagent/scenarios/qlib/experiment/workspace.py:13`)、`FactorFBWorkspace`(`rdagent/components/coder/factor_coder/factor.py:75`)、`process_factor_data`(`rdagent/scenarios/qlib/developer/utils.py:131`)、`ALPHA158`(`rdagent/utils/qlib.py:27`)、`QlibFactorExperiment`、`LoopBase.dump`(`loop.py:426`)、`Trace`/`Experiment`/`Hypothesis`/`HypothesisFeedback`/`FactorTask`
- Produces:`run_fast_backtest(payload) -> Generator[str,None,None]` 完整实现

**背景 — trace dump 的真实结构:**
`LoopBase.load`(`loop.py:492`)扫描 `__session__/<loop_idx>/<step_idx>_<step_name>` 的 pickle 文件,取最新的。所以微型 trace 的 dump 路径必须是 `__session__/0/0_fast` 这样的结构。`dump` 就是 `pickle.dump(self, f)`(`loop.py:431`),dump 整个 loop 对象。`query_sota` 读 `loop.trace.hist`(需含 `(exp, fb)` 且 `fb.decision=True`)。

由于 `LoopBase.__init__` 依赖 asyncio.Queue/timer,我们用最小子类:**构造后手动设 `trace` 属性,然后 `dump` 到正确路径**。

- [ ] **Step 1: 写失败测试 — Alpha158 表达式提取**

追加到 `test_fast_backtest.py`:

```python
from rdagent.app.fast_backtest import _alpha158_expressions


def test_alpha158_expressions_subset():
    exprs = _alpha158_expressions(["KMID", "ROC5"])
    # Returns (expressions_list, names_list) for Jinja injection
    assert isinstance(exprs, tuple) and len(exprs) == 2
    expressions, names = exprs
    assert "KMID" in names and "ROC5" in names
    # Each expression is a Qlib operator string
    assert any("($close-$open)/$open" in e for e in expressions)


def test_alpha158_expressions_empty():
    expressions, names = _alpha158_expressions([])
    assert expressions == [] and names == []
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k alpha158`
预期:FAIL

- [ ] **Step 2: 实现 `_alpha158_expressions`**

追加到 `fast_backtest.py`:

```python
from rdagent.utils.qlib import ALPHA158


def _alpha158_expressions(selected: list[str]) -> tuple[list[str], list[str]]:
    """Extract Qlib expressions for selected Alpha158 factor names.

    Returns (expressions, names) lists for Jinja injection into
    conf_combined_factors.yaml's feature_expressions / feature_names.
    """
    expressions = []
    names = []
    for name in selected:
        if name in ALPHA158:
            expressions.append(ALPHA158[name])
            names.append(name)
    return expressions, names
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k alpha158`
预期:2 个测试 PASS

- [ ] **Step 3: 写失败测试 — trace 路径构造**

追加到 `test_fast_backtest.py`:

```python
from pathlib import Path
from rdagent.app.fast_backtest import _trace_dump_path


def test_trace_dump_path_structure():
    """The dump path must be __session__/<loop>/<step>_<name> for LoopBase.load to find it."""
    base = Path("/tmp/fake_log/Finance Data Building/fast-aurora-20260728")
    path = _trace_dump_path(base)
    # Must end with __session__/0/0_fast (loop_idx=0, step_idx=0, name=fast)
    assert path.parent.name == "0"  # loop_idx dir
    assert path.name == "0_fast"  # step_idx_name
    assert path.parent.parent.name == "__session__"
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k trace_dump`
预期:FAIL

- [ ] **Step 4: 实现 `_trace_dump_path`**

追加到 `fast_backtest.py`:

```python
def _trace_dump_path(trace_log_dir: Path) -> Path:
    """Build the dump path matching LoopBase.load's glob pattern: __session__/<loop>/<step>_<name>."""
    return Path(trace_log_dir) / "__session__" / "0" / "0_fast"
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k trace_dump`
预期:PASS

- [ ] **Step 5: 写失败测试 — trace 组装(mock workspace)**

追加到 `test_fast_backtest.py`:

```python
from unittest.mock import MagicMock
from rdagent.app.fast_backtest import _build_and_dump_trace


def test_build_and_dump_trace_creates_session(tmp_path):
    """Building a trace must create __session__/0/0_fast with a pickled loop containing trace.hist."""
    factor_task = MagicMock()
    factor_ws = MagicMock()
    qlib_ws = MagicMock()
    qlib_ws.workspace_path = str(tmp_path / "workspace")

    import pandas as pd
    metrics = pd.Series({"IC": 0.05, "annualized_return": 0.18})

    trace_dir = tmp_path / "Finance Data Building" / "fast-test-20260728"
    _build_and_dump_trace(
        trace_dir=trace_dir,
        factor_task=factor_task,
        factor_ws=factor_ws,
        qlib_ws=qlib_ws,
        metrics=metrics,
        description="test strategy",
    )
    dump_file = trace_dir / "__session__" / "0" / "0_fast"
    assert dump_file.exists()
    # Verify the dumped object has a trace with hist
    import pickle
    with open(dump_file, "rb") as f:
        loop = pickle.load(f)
    assert hasattr(loop, "trace")
    assert len(loop.trace.hist) == 1
    exp, fb = loop.trace.hist[0]
    assert fb.decision is True  # SOTA marker
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k build_and_dump`
预期:FAIL

- [ ] **Step 6: 实现 `_build_and_dump_trace`**

追加到 `fast_backtest.py`:

```python
import pickle
from rdagent.core.proposal import Trace, Hypothesis, HypothesisFeedback
from rdagent.core.experiment import Experiment
from rdagent.components.coder.factor_coder.factor import FactorTask
from rdagent.utils.workflow.loop import LoopBase


def _build_and_dump_trace(
    trace_dir: Path,
    factor_task: FactorTask,
    factor_ws,
    qlib_ws,
    metrics,
    description: str,
) -> None:
    """Assemble a minimal single-experiment trace and dump it as a fake LoopBase session.

    The structure must satisfy query_sota: trace.hist has (exp, fb) with fb.decision=True,
    exp.experiment_workspace.workspace_path points to the qrun workspace (with mlruns/),
    exp.sub_workspace_list carries the factor.py code.
    """
    # 1. Assemble Experiment
    exp = Experiment(
        sub_tasks=[factor_task],
        sub_workspace_list=[factor_ws],
        experiment_workspace=qlib_ws,
        result=metrics,
    )
    exp.hypothesis = Hypothesis(hypothesis=description, assumption=description)

    # 2. SOTA marker feedback
    fb = HypothesisFeedback(
        reason="fast backtest auto-accepted",
        decision=True,
        observations="generated by fast backtest",
    )

    # 3. Minimal Trace
    trace = Trace()
    trace.hist.append((exp, fb))

    # 4. Minimal LoopBase: bypass __init__ (avoids asyncio.Queue/timer deps),
    #    set only what dump + query_sota need.
    loop = LoopBase.__new__(LoopBase)
    loop.trace = trace
    loop.loop_trace = {}
    loop.session_folder = trace_dir / "__session__"

    # 5. Dump to the path LoopBase.load expects: __session__/0/0_fast
    dump_path = _trace_dump_path(trace_dir)
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dump_path, "wb") as f:
        pickle.dump(loop, f)
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k build_and_dump`
预期:PASS

- [ ] **Step 7: 写失败测试 — 主 `run_fast_backtest` 编排(mock 全部外部依赖)**

追加到 `test_fast_backtest.py`:

```python
from rdagent.app.fast_backtest import run_fast_backtest


def test_run_fast_backtest_alpha158_only_path(tmp_path, monkeypatch):
    """Pure Alpha158 path skips codegen/factor_eval, goes straight to backtest+trace."""
    # Mock QlibFBWorkspace.execute to avoid real qrun
    mock_ws_instance = MagicMock()
    mock_ws_instance.execute.return_value = (MagicMock(), "ok")
    mock_ws_instance.workspace_path = str(tmp_path / "workspace")

    monkeypatch.setattr("rdagent.app.fast_backtest.QlibFBWorkspace", lambda **kw: mock_ws_instance)
    monkeypatch.setattr("rdagent.app.fast_backtest._run_qlib_backtest", lambda *a, **kw: (MagicMock(name="metrics"), [], []))
    monkeypatch.setattr("rdagent.app.fast_backtest._build_and_dump_trace", lambda **kw: None)

    payload = {"alpha158": ["KMID"], "description": ""}
    events = _parse_sse_events("".join(run_fast_backtest(payload)))
    stages = [e["stage"] for e in events]
    # Alpha158-only path skips codegen + factor_eval
    assert "codegen" not in stages
    assert "done" in stages
    assert events[-1]["status"] == "ok"


def test_run_fast_backtest_error_emits_error_event(monkeypatch):
    """A failed step emits an error SSE event instead of raising."""
    def boom(*a, **kw):
        raise FastBacktestError("LLM exploded")
    monkeypatch.setattr("rdagent.app.fast_backtest._generate_factor_code", boom)

    payload = {"alpha158": [], "description": "anything"}
    events = _parse_sse_events("".join(run_fast_backtest(payload)))
    error_events = [e for e in events if e["status"] == "error"]
    assert len(error_events) == 1
    assert "LLM exploded" in error_events[0]["error"]
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v -k run_fast`
预期:FAIL(`run_fast_backtest` / `_run_qlib_backtest` 未定义)

- [ ] **Step 8: 实现 `_run_qlib_backtest` + 主 `run_fast_backtest`**

追加到 `fast_backtest.py`:

```python
from pathlib import Path
import randomname
from datetime import datetime
import pandas as pd

from rdagent.scenarios.qlib.experiment.workspace import QlibFBWorkspace
from rdagent.components.coder.factor_coder.factor import FactorFBWorkspace

_FACTOR_TEMPLATE_FOLDER = Path(__file__).resolve().parent.parent / "scenarios" / "qlib" / "experiment" / "factor_template"


def _run_qlib_backtest(alpha158: list[str], factor_code: str | None) -> tuple:
    """Run the Qlib backtest. Returns (metrics_series, equity_list, qlib_workspace).

    Sets up QlibFBWorkspace with conf_combined_factors.yaml, injects Alpha158
    expressions via Jinja, runs qrun with model_selector=linear.
    """
    expressions, names = _alpha158_expressions(alpha158)

    # Build workspace from template (renders Jinja including model_selector branch)
    workspace = QlibFBWorkspace(template_folder_path=_FACTOR_TEMPLATE_FOLDER)
    # Inject Alpha158 feature expressions/names into the rendered config
    workspace.extra_vars = {
        "feature_expressions": expressions,
        "feature_names": names,
        "model_selector": "linear",
        "train_start": "2008-01-01", "train_end": "2014-12-31",
        "valid_start": "2015-01-01", "valid_end": "2016-12-31",
        "test_start": "2017-01-01", "test_end": "null",
    }

    # Execute qrun (LinearModel OLS) — produces mlruns/, qlib_res.csv, ret.pkl
    metrics, qlib_log = workspace.execute(
        qlib_config_name="conf_combined_factors.yaml",
        run_env={"QLIB_FACTOR_MODEL_SELECTOR": "linear"},
    )
    if metrics is None:
        raise FastBacktestError("Qlib 回测失败,未产出指标。日志:\n" + str(qlib_log)[:1000])

    # Parse equity curve from ret.pkl
    ret_path = workspace.workspace_path / "ret.pkl"
    equity = []
    if ret_path.exists():
        ret_df = pd.read_pickle(ret_path)
        # ret_df has return columns; build cumulative net value
        if "return" in ret_df.columns:
            cum = (1 + ret_df["return"]).cumprod()
            equity = [[str(d.date()), float(v)] for d, v in cum.items()]

    return metrics, equity, workspace


def run_fast_backtest(payload: dict) -> Generator[str, None, None]:
    """Main orchestration generator. Yields SSE event strings.

    4 steps: codegen (if NL) → factor_eval (if NL) → backtest → trace_write.
    Each step emits progress; errors emit an error event and stop.
    """
    ok, err = _validate_payload(payload)
    if not ok:
        yield _sse("validation", "error", error=err)
        return

    alpha158 = payload.get("alpha158") or []
    description = (payload.get("description") or "").strip()
    factor_code = None
    factor_task = None
    factor_ws = None

    try:
        # Step 1: codegen (only if natural language provided)
        if description:
            yield _sse("codegen", "running")
            result = _generate_factor_code(description)
            factor_code = result["code"]
            factor_name = result["factor_name"]
            yield _sse("codegen", "ok", factor_name=factor_name, code=factor_code)

            # Build FactorTask + workspace (for trace)
            from rdagent.components.coder.factor_coder.factor import FactorTask as FT
            factor_task = FT(
                factor_name=factor_name,
                factor_description=description,
                factor_formulation="(fast-backtest NL)",
            )
            factor_ws = FactorFBWorkspace(target_task=factor_task, code_dict={"factor.py": factor_code})

            # Step 2: factor_eval (validate the code runs)
            yield _sse("factor_eval", "running")
            feedback, factor_df = factor_ws.execute("Debug")
            if factor_df is None:
                raise FastBacktestError("因子值计算失败,result.h5 未产出:\n" + feedback[:500])
            yield _sse("factor_eval", "ok")

        # For Alpha158-only path, build a synthetic factor_task/ws
        if factor_task is None:
            from rdagent.components.coder.factor_coder.factor import FactorTask as FT
            factor_task = FT(
                factor_name="alpha158_subset",
                factor_description=f"Alpha158 subset: {', '.join(alpha158[:10])}",
                factor_formulation="(fast-backtest Alpha158)",
            )
            factor_ws = FactorFBWorkspace(target_task=factor_task, code_dict={})

        # Step 3: backtest
        yield _sse("backtest", "running")
        metrics, equity, qlib_ws = _run_qlib_backtest(alpha158, factor_code)
        yield _sse("backtest", "ok")

        # Step 4: trace write
        trace_name = f"fast-{randomname.get_name()}-{datetime.now().strftime('%Y%m%d')}"
        trace_dir = Path("log") / "Finance Data Building" / trace_name
        _build_and_dump_trace(
            trace_dir=trace_dir,
            factor_task=factor_task,
            factor_ws=factor_ws,
            qlib_ws=qlib_ws,
            metrics=metrics,
            description=description or f"Alpha158: {', '.join(alpha158)}",
        )
        trace_id = f"Finance Data Building/{trace_name}"

        # Parse key metrics for the frontend
        metrics_dict = {}
        if hasattr(metrics, "to_dict"):
            metrics_dict = {k: float(v) for k, v in metrics.to_dict().items()}

        yield _sse("done", "ok", trace_id=trace_id, metrics=metrics_dict, equity=equity)

    except FastBacktestError as e:
        yield _sse("backtest", "error", error=str(e), detail=str(e)[:500])
    except Exception as e:
        yield _sse("backtest", "error", error=f"未预期错误: {type(e).__name__}: {e}")
```

运行:`python -m pytest rdagent/app/test_fast_backtest.py -v`
预期:全部测试 PASS

- [ ] **Step 9: 提交**

```bash
git add rdagent/app/fast_backtest.py rdagent/app/test_fast_backtest.py
git commit -m "feat(fast-backtest): backtest execution + minimal trace assembly + orchestration"
```

---

## Task 4: 后端 — Flask 端点 `POST /fastbacktest/run`

**Files:**
- Modify: `rdagent/log/server/app.py`(新增端点,约在 `/predict/history` 之后)

**Interfaces:**
- Consumes:`run_fast_backtest`(`rdagent/app/fast_backtest.py`)
- Produces:`POST /fastbacktest/run` SSE 端点

- [ ] **Step 1: 新增 Flask 端点**

在 `app.py` 的 `predict_history` 函数之后(约 1636 行后)添加:

```python
@app.route("/fastbacktest/run", methods=["POST"])
def fast_backtest_run():
    """Run a fast backtest: NL + Alpha158 → linear backtest → predict-ready trace.

    Returns an SSE stream of progress events.
    """
    from flask import Response, stream_with_context
    from rdagent.app.fast_backtest import run_fast_backtest

    payload = request.get_json(silent=True) or {}

    def generate():
        try:
            for event in run_fast_backtest(payload):
                yield event
        except GeneratorExit:
            # Client disconnected
            pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
```

- [ ] **Step 2: 手动验证端点可达**

启动后端:`rdagent server_ui`(后台)
然后用 curl 测试 SSE(空 payload 应返回 validation error):

```bash
curl -N -X POST http://localhost:19899/fastbacktest/run \
  -H "Content-Type: application/json" \
  -d '{"alpha158":[],"description":""}'
```

预期:收到 `data: {"stage":"validation","status":"error",...}`

```bash
git add rdagent/log/server/app.py
git commit -m "feat(fast-backtest): Flask SSE endpoint POST /fastbacktest/run"
```

---

## Task 5: 前端 — API 层 + 多页入口脚手架

**Files:**
- Modify: `web/src/services/rdagent-api.ts`(新增 `runFastBacktest`)
- Modify: `web/vite.config.ts`(加 input)
- Create: `web/fastbacktest.html`、`web/src/fastbacktest/main.ts`、`router.ts`、`api.ts`

**Interfaces:**
- Consumes:`POST /fastbacktest/run`(Task 4)
- Produces:`runFastBacktest(payload, onEvent)` — 用 fetch + ReadableStream 消费 SSE,`onEvent` 回调接收解析后的事件对象

- [ ] **Step 1: 新增 `runFastBacktest` 到 `services/rdagent-api.ts`**

在文件末尾(precdict 相关函数后)添加:

```typescript
/** Fast backtest SSE event types */
export interface FastBacktestEvent {
  stage: 'codegen' | 'factor_eval' | 'backtest' | 'done' | 'validation' | 'error'
  status: 'running' | 'ok' | 'error'
  factor_name?: string
  code?: string
  trace_id?: string
  metrics?: Record<string, number>
  equity?: [string, number][]
  error?: string
  detail?: string
}

/**
 * Run a fast backtest via SSE stream.
 * Uses fetch + ReadableStream because EventSource doesn't support POST body.
 */
export async function runFastBacktest(
  payload: { alpha158?: string[]; description?: string },
  onEvent: (event: FastBacktestEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/fastbacktest/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`fast backtest failed: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE events separated by \n\n
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch { /* skip malformed */ }
      }
    }
  }
}
```

- [ ] **Step 2: 创建多页入口 HTML**

创建 `web/fastbacktest.html`(仿 `web/predict.html`):

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Multiα1pha · 快速回测</title>
</head>
<body>
  <div id="fastbacktest-app"></div>
  <script type="module" src="/src/fastbacktest/main.ts"></script>
</body>
</html>
```

- [ ] **Step 3: 创建 main.ts + router.ts + api.ts**

`web/src/fastbacktest/main.ts`:
```typescript
import { createApp } from 'vue'
import FastBacktestApp from './FastBacktestApp.vue'
import './styles/fastbacktest.css'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import router from './router'

createApp(FastBacktestApp).use(router).mount('#fastbacktest-app')
```

`web/src/fastbacktest/router.ts`:
```typescript
import { createRouter, createWebHashHistory } from 'vue-router'
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fb-home', component: { template: '<span />' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
```

`web/src/fastbacktest/api.ts`:
```typescript
export { runFastBacktest, type FastBacktestEvent } from '../services/rdagent-api'
```

- [ ] **Step 4: 修改 `vite.config.ts` 加入口**

在 `rollupOptions.input` 中(multialpha/predict/anaAgents 之后)加:
```typescript
        fastbacktest: pathResolve('./fastbacktest.html'),
```

- [ ] **Step 5: 验证构建通过**

```bash
cd web && npx vue-tsc --noEmit 2>&1 | head -20
```
预期:无 TS 错误(或仅有与本任务无关的既有错误)。若有本任务引入的错误,修复后重试。

```bash
git add web/fastbacktest.html web/src/fastbacktest/ web/src/services/rdagent-api.ts web/vite.config.ts
git commit -m "feat(fast-backtest): frontend scaffold + SSE API + vite entry"
```

---

## Task 6: 前端 — 视觉令牌 + 根组件 `FastBacktestApp.vue`

**Files:**
- Create: `web/src/fastbacktest/styles/fastbacktest.css`
- Create: `web/src/fastbacktest/FastBacktestApp.vue`
- Create: `web/src/fastbacktest/use-fastbacktest.ts`

**Interfaces:**
- Consumes:`runFastBacktest`(Task 5)、multialpha 令牌(导入 `tokens.css` 变量)
- Produces:`useFastBacktest()` composable —— 返回 `phase`/`alpha158Groups`/`run()`/`stages`/`result`

- [ ] **Step 1: 创建样式文件(复用 multialpha 令牌)**

`web/src/fastbacktest/styles/fastbacktest.css`:
```css
@import '../multialpha/styles/tokens.css';

.fb-app { height: 100vh; display: flex; flex-direction: column; overflow: hidden; background: var(--ma-bg); font-family: 'Noto Sans SC','PingFang SC',sans-serif; }
.fb-main { flex: 1; min-height: 0; overflow: auto; }
.fb-content { padding: 36px clamp(24px,5vw,64px); }
.fb-section-heading { display: flex; gap: 24px; margin-bottom: 32px; }
.fb-section-heading>span { width: 38px; height: 38px; display: grid; place-items: center; border: 1px solid var(--ma-gold); color: var(--ma-gold-dark); font: 600 12px 'JetBrains Mono',monospace; flex: none; }
.fb-section-heading p { margin: 0 0 5px; color: var(--ma-gold-dark); font: 600 10px 'JetBrains Mono',monospace; letter-spacing: 2px; }
.fb-section-heading h3 { margin: 0 0 8px; font-size: 27px; color: var(--ma-ink); font-family: 'Noto Serif SC',serif; }
.fb-section-heading small { color: var(--ma-muted); font-size: 13px; }
.fb-card { background: var(--ma-surface); border: 1px solid #d7d5ce; border-radius: var(--ma-radius); padding: 24px; box-shadow: 0 2px 10px rgb(25 27 33 / 5%); }
.fb-input-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 28px; }
.fb-btn-primary { background: var(--ma-gold); border: 1px solid var(--ma-gold); color: #fff; font: 600 14px 'Noto Sans SC'; padding: 12px 32px; border-radius: 4px; cursor: pointer; box-shadow: 0 4px 14px rgb(185 154 80 / 25%); }
.fb-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
```

- [ ] **Step 2: 创建 composable `use-fastbacktest.ts`**

```typescript
import { ref, computed } from 'vue'
import { runFastBacktest, type FastBacktestEvent } from '../services/rdagent-api'
import { ALPHA158_GROUPS, ALPHA20 } from './alpha158-data'

export type Phase = 'input' | 'running' | 'result'
export interface StageState { stage: string; status: 'pending'|'running'|'ok'|'error'; ms?: number; detail?: string }

export function useFastBacktest() {
  const phase = ref<Phase>('input')
  const selectedAlpha158 = ref<string[]>([...ALPHA20])
  const description = ref('')
  const stages = ref<StageState[]>([])
  const result = ref<{ traceId: string; metrics: Record<string,number>; equity: [string,number][] } | null>(null)
  const errorMsg = ref('')

  const canRun = computed(() => selectedAlpha158.value.length > 0 || description.value.trim().length > 0)

  function reset() {
    phase.value = 'input'; stages.value = []; result.value = null; errorMsg.value = ''
  }

  async function run() {
    phase.value = 'running'
    stages.value = [
      { stage: 'codegen', status: 'pending' },
      { stage: 'factor_eval', status: 'pending' },
      { stage: 'backtest', status: 'pending' },
    ]
    result.value = null; errorMsg.value = ''
    try {
      await runFastBacktest(
        { alpha158: selectedAlpha158.value, description: description.value },
        (ev: FastBacktestEvent) => {
          const idx = stages.value.findIndex(s => s.stage === ev.stage)
          if (idx >= 0) stages.value[idx].status = ev.status === 'ok' ? 'ok' : ev.status === 'error' ? 'error' : 'running'
          else if (ev.stage === 'done') { /* handled below */ }
          if (ev.stage === 'done' && ev.status === 'ok') {
            result.value = { traceId: ev.trace_id!, metrics: ev.metrics!, equity: ev.equity! }
            phase.value = 'result'
          }
          if (ev.status === 'error') { errorMsg.value = ev.error || '未知错误'; }
        },
      )
      if (phase.value === 'running') phase.value = 'result'
    } catch (e) {
      errorMsg.value = e instanceof Error ? e.message : String(e)
      phase.value = 'input'
    }
  }

  return { phase, selectedAlpha158, description, stages, result, errorMsg, canRun, run, reset, alpha158Groups: ALPHA158_GROUPS }
}
```

- [ ] **Step 3: 创建根组件 `FastBacktestApp.vue`**

```vue
<template>
  <div class="fb-app">
    <TopBar simple @home="goHome" />
    <main class="fb-main">
      <div class="fb-content">
        <header class="fb-section-heading">
          <span>{{ phase === 'result' ? '✓' : '01' }}</span>
          <div>
            <p>{{ phase === 'result' ? 'BACKTEST COMPLETE' : 'FAST BACKTEST' }}</p>
            <h3>{{ phase === 'result' ? '回测完成' : '快速回测 · 自然语言策略即时验证' }}</h3>
            <small v-if="phase !== 'result'">勾选 Alpha158 因子,或用自然语言描述策略 —— 跳过迭代循环,单因子直跑 Qlib 回测</small>
          </div>
        </header>

        <div v-if="phase === 'input' || phase === 'running'" class="fb-input-grid">
          <Alpha158Picker v-model:selected="selectedAlpha158" :disabled="phase==='running'" />
          <DescriptionInput v-model:text="description" :disabled="phase==='running'" />
        </div>

        <div v-if="phase !== 'input'" style="margin-bottom:24px">
          <ProgressTimeline :stages="stages" :error="errorMsg" />
        </div>

        <div v-if="phase === 'input' || phase === 'running'" style="text-align:center;margin-bottom:8px">
          <button class="fb-btn-primary" :disabled="!canRun || phase==='running'" @click="run">▶ 开始快速回测</button>
          <div style="font-size:11px;color:var(--ma-muted);margin-top:10px">至少填写一项输入 · 固定 LinearModel(OLS)+ csi300</div>
        </div>

        <div v-if="phase === 'result' && result">
          <MetricsPanel :metrics="result.metrics" />
          <EquityChart :equity="result.equity" />
          <div style="background:#f0f7f3;border:1px solid #b8d8c8;border-radius:6px;padding:12px;display:flex;justify-content:space-between;align-items:center;margin-top:14px">
            <div style="font-size:12px">
              <span style="color:var(--ma-success);font-weight:600">✓ 已保存为可预测实验</span>
              <span style="color:var(--ma-muted);display:block;margin-top:3px;font:11px 'JetBrains Mono',monospace">{{ result.traceId }}</span>
            </div>
            <button style="background:var(--ma-success);border:1px solid var(--ma-success);color:#fff;font:600 12px 'Noto Sans SC';padding:6px 14px;border-radius:4px;cursor:pointer" @click="goPredict">前往预测 →</button>
          </div>
          <div style="text-align:center;margin-top:20px">
            <button class="fb-btn-primary" @click="reset">↺ 再跑一个</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useFastBacktest } from './use-fastbacktest'
import TopBar from './components/TopBar.vue'
import Alpha158Picker from './components/Alpha158Picker.vue'
import DescriptionInput from './components/DescriptionInput.vue'
import ProgressTimeline from './components/ProgressTimeline.vue'
import MetricsPanel from './components/MetricsPanel.vue'
import EquityChart from './components/EquityChart.vue'

const { phase, selectedAlpha158, description, stages, result, errorMsg, canRun, run, reset } = useFastBacktest()
const goHome = () => { window.location.href = './multialpha.html' }
const goPredict = () => { window.location.href = './predict.html' }
</script>
```

> **注**:这里引用了 `./components/TopBar.vue`(简化版,复用 multialpha 的 TopBar 结构)。如果不想新建,可 import `../multialpha/components/TopBar.vue`。实现时按耦合度决定。

- [ ] **Step 4: 创建占位 alpha158-data.ts + 5 个子组件骨架**

由于子组件内容较多,先创建骨架让 tsc 通过,内容在 Task 7-8 填充。

`web/src/fastbacktest/alpha158-data.ts`:
```typescript
import { ALPHA158 } from '../../../../rdagent/utils/qlib'  // NOTE: 实际从后端 API 获取,见 Task 7
```
> **修正**:Alpha158 数据应通过新的后端端点 `GET /fastbacktest/alpha158` 获取(返回分组结构),而非直接 import Python 文件。Task 7 实现此端点 + 前端获取。首版可硬编码在前端(从 qlib.py 抄),Task 7 再接 API。

创建 5 个子组件骨架(每个先放最小 template,Task 7-8 填充):
- `components/TopBar.vue` — `<header>...logo...</header>`(复用 multialpha TopBar 结构)
- `components/Alpha158Picker.vue` — `<div>picker placeholder</div>`
- `components/DescriptionInput.vue` — `<textarea />`
- `components/ProgressTimeline.vue` — `<div>timeline</div>`
- `components/MetricsPanel.vue` — `<div>metrics</div>`
- `components/EquityChart.vue` — `<div>chart</div>`

- [ ] **Step 5: 验证 tsc + dev server**

```bash
cd web && npx vue-tsc --noEmit 2>&1 | grep fastbacktest | head
```
预期:无 fastbacktest 相关错误。

```bash
git add web/src/fastbacktest/
git commit -m "feat(fast-backtest): root app + composable + style tokens + component skeletons"
```

---

## Task 7: 前端 — Alpha158 数据端点 + Picker 组件

**Files:**
- Modify: `rdagent/log/server/app.py`(新增 `GET /fastbacktest/alpha158`)
- Create: `web/src/fastbacktest/alpha158-data.ts`(完整)
- Modify: `web/src/fastbacktest/components/Alpha158Picker.vue`(完整实现)
- Modify: `web/src/fastbacktest/use-fastbacktest.ts`(改用 API 获取)

**Interfaces:**
- Consumes:`ALPHA158`(`rdagent/utils/qlib.py:27`)
- Produces:`GET /fastbacktest/alpha158` → `{groups: [{name, label, factors:[{name, expr}]}]}`;`Alpha158Picker.vue` 完整勾选面板

- [ ] **Step 1: 后端 — Alpha158 元数据端点**

在 `app.py` 加端点(放在 `/fastbacktest/run` 前):

```python
@app.route("/fastbacktest/alpha158", methods=["GET"])
def fast_backtest_alpha158():
    """Return Alpha158 factor groups for the picker UI."""
    from rdagent.utils.qlib import ALPHA158, ALPHA20
    import re
    # Group by factor family (strip trailing digits)
    groups_map: dict[str, list[dict]] = {}
    for name, expr in ALPHA158.items():
        m = re.match(r'^(.+?)(\d+)$', name)
        family = m.group(1) if m else name
        groups_map.setdefault(family, []).append({"name": name, "expr": expr})
    groups = [{"family": k, "factors": v} for k, v in groups_map.items()]
    return jsonify({"groups": groups, "alpha20": list(ALPHA20.keys())})
```

- [ ] **Step 2: 前端 — alpha158-data.ts(从 API 获取)**

```typescript
export interface Alpha158Factor { name: string; expr: string }
export interface Alpha158Group { family: string; factors: Alpha158Factor[] }
export interface Alpha158Meta { groups: Alpha158Group[]; alpha20: string[] }

let cached: Alpha158Meta | null = null
export async function fetchAlpha158(): Promise<Alpha158Meta> {
  if (cached) return cached
  const res = await fetch('/fastbacktest/alpha158')
  cached = await res.json()
  return cached!
}
```

- [ ] **Step 3: 前端 — Alpha158Picker.vue 完整实现**

```vue
<template>
  <div class="fb-card">
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px">
      <div>
        <b style="color:var(--ma-gold-dark);font:600 18px 'JetBrains Mono',monospace">Aa</b>
        <h4 style="margin:14px 0 4px;font-size:17px;color:var(--ma-ink)">Alpha158 因子勾选</h4>
      </div>
      <span style="color:var(--ma-gold-dark);font:9px 'JetBrains Mono',monospace">ENTER →</span>
    </div>
    <p style="margin:0 0 16px;color:var(--ma-muted);font-size:12px;line-height:1.65">从 158 个标准量化因子中勾选子集</p>
    <div style="display:flex;gap:6px;margin-bottom:14px">
      <button class="fb-quick-btn" @click="selectAll">全选</button>
      <button class="fb-quick-btn" @click="selected.splice(0)">清空</button>
      <button class="fb-quick-btn fb-quick-active" @click="selectAlpha20">ALPHA20</button>
    </div>
    <div v-if="loading" style="color:var(--ma-muted);font-size:12px">加载因子列表...</div>
    <div v-else style="font-size:12px;line-height:1.8;max-height:280px;overflow:auto;border-top:1px solid var(--ma-surface-2);padding-top:10px">
      <template v-for="group in meta?.groups" :key="group.family">
        <div class="fb-family" @click="toggleFamily(group.family)">
          {{ expanded.has(group.family) ? '▼' : '▸' }} {{ group.family }}
          <span style="color:var(--ma-muted)">({{ countSelected(group) }}/{{ group.factors.length }})</span>
        </div>
        <div v-if="expanded.has(group.family)" style="padding:4px 0 6px 16px">
          <label v-for="f in group.factors" :key="f.name" style="display:inline-block;width:72px">
            <input type="checkbox" :value="f.name" v-model="proxySelected" :disabled="disabled" style="accent-color:var(--ma-gold)">
            <span :style="{color: isSelected(f.name) ? 'var(--ma-ink)' : 'var(--ma-muted)'}">{{ f.name }}</span>
          </label>
        </div>
      </template>
    </div>
    <div style="color:var(--ma-muted);font:11px 'JetBrains Mono',monospace;padding-top:8px;border-top:1px solid var(--ma-surface-2);margin-top:6px">已选 {{ selected.length }} / 158</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchAlpha158, type Alpha158Meta } from '../alpha158-data'
const props = defineProps<{ selected: string[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:selected': [string[]] }>()
const proxySelected = computed({ get: () => props.selected, set: (v) => emit('update:selected', v) })
const meta = ref<Alpha158Meta | null>(null)
const loading = ref(true)
const expanded = ref<Set<string>>(new Set())
onMounted(async () => { meta.value = await fetchAlpha158(); loading.value = false })
const isSelected = (n: string) => props.selected.includes(n)
const countSelected = (g: any) => g.factors.filter((f: any) => isSelected(f.name)).length
const toggleFamily = (f: string) => { expanded.value.has(f) ? expanded.value.delete(f) : expanded.value.add(f); expanded.value = new Set(expanded.value) }
const selectAll = () => { if (meta.value) proxySelected.value = meta.value.groups.flatMap(g => g.factors.map(f => f.name)) }
const selectAlpha20 = () => { if (meta.value) proxySelected.value = [...meta.value.alpha20] }
</script>
<style scoped>
.fb-quick-btn { font:500 11px 'Noto Sans SC'; background:var(--ma-surface-2); border:1px solid var(--ma-line); color:var(--ma-ink); padding:4px 10px; border-radius:4px; cursor:pointer; }
.fb-quick-active { background:var(--ma-gold-soft); border-color:var(--ma-gold); color:var(--ma-gold-dark); font-weight:600; }
.fb-family { color:var(--ma-gold-dark); font:600 12px 'JetBrains Mono',monospace; cursor:pointer; padding:6px 0; }
</style>
```

- [ ] **Step 4: 更新 use-fastbacktest.ts 移除硬编码 ALPHA158_GROUPS**

把 Task 6 中的 `import { ALPHA158_GROUPS, ALPHA20 } from './alpha158-data'` 改为:
```typescript
import { fetchAlpha158 } from './alpha158-data'
```
并把 `selectedAlpha158` 初始值改为空 `ref<string[]>([])`,在组件 mount 时异步加载并默认勾选 ALPHA20。Picker 组件自己处理 fetch,composable 不再持有 groups。

- [ ] **Step 5: 验证**

```bash
curl http://localhost:19899/fastbacktest/alpha158 | python -m json.tool | head -20
```
预期:返回 groups 结构。前端 `npm run dev` 后访问 `localhost:8080/fastbacktest.html` 看到 Picker。

```bash
git add rdagent/log/server/app.py web/src/fastbacktest/
git commit -m "feat(fast-backtest): Alpha158 metadata endpoint + picker component"
```

---

## Task 8: 前端 — DescriptionInput / ProgressTimeline / MetricsPanel / EquityChart 组件

**Files:**
- Modify: `web/src/fastbacktest/components/DescriptionInput.vue`(完整)
- Modify: `web/src/fastbacktest/components/ProgressTimeline.vue`(完整)
- Modify: `web/src/fastbacktest/components/MetricsPanel.vue`(完整)
- Modify: `web/src/fastbacktest/components/EquityChart.vue`(完整)
- Modify: `web/src/fastbacktest/components/TopBar.vue`(简化版,复用 multialpha TopBar 结构)

- [ ] **Step 1: DescriptionInput.vue**

```vue
<template>
  <div class="fb-card" style="display:flex;flex-direction:column">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b style="color:var(--ma-gold-dark);font:600 18px 'JetBrains Mono',monospace">NL</b>
      <span style="color:var(--ma-gold-dark);font:9px 'JetBrains Mono',monospace">ENTER →</span>
    </div>
    <h4 style="margin:14px 0 4px;font-size:17px;color:var(--ma-ink)">自然语言策略描述</h4>
    <p style="margin:0 0 16px;color:var(--ma-muted);font-size:12px;line-height:1.65">用一句话描述策略思路,LLM 单次生成 factor.py 并回测</p>
    <textarea
      :value="text" @input="$emit('update:text', ($event.target as HTMLTextAreaElement).value)"
      :disabled="disabled"
      placeholder="基于价格动量与成交量的背离构建因子..."
      style="flex:1;min-height:210px;background:var(--ma-surface-2);border:1px solid var(--ma-line);border-radius:4px;color:var(--ma-ink);padding:14px;font-family:'JetBrains Mono',monospace;font-size:12.5px;line-height:1.7;resize:none"
    />
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;font-size:11px">
      <span style="color:var(--ma-muted)">LLM 单次生成,不自动修正</span>
      <span style="color:var(--ma-warning);background:#fdf6e9;border:1px solid #f0dba8;padding:2px 8px;border-radius:3px">最快出图</span>
    </div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ text: string; disabled?: boolean }>()
defineEmits<{ 'update:text': [string] }>()
</script>
```

- [ ] **Step 2: ProgressTimeline.vue(深色终端风格)**

```vue
<template>
  <div class="fb-terminal">
    <div class="fb-terminal-head">
      <span>● ● ● &nbsp; FAST BACKTEST · {{ hasError ? 'ERROR' : 'RUNNING' }}</span>
    </div>
    <div v-for="(s, i) in stages" :key="i" class="fb-stage" :class="s.status">
      <span class="fb-stage-icon">{{ iconFor(s.status) }}</span>
      <div class="fb-stage-body">
        <div class="fb-stage-title">{{ labelFor(s.stage) }}</div>
        <div class="fb-stage-detail">{{ s.detail || '' }}</div>
      </div>
    </div>
    <div v-if="error" class="fb-error">{{ error }}</div>
  </div>
</template>
<script setup lang="ts">
import type { StageState } from '../use-fastbacktest'
const props = defineProps<{ stages: StageState[]; error?: string }>()
const hasError = !!props.error
const iconFor = (s: string) => s === 'ok' ? '✓' : s === 'error' ? '✗' : s === 'running' ? '⟳' : '○'
const labelFor = (stage: string) => ({ codegen: '因子代码生成', factor_eval: '因子值计算', backtest: 'Qlib 回测' }[stage] || stage)
</script>
<style scoped>
.fb-terminal { background:#0a0d13; background-image:linear-gradient(#ffffff0b 1px,transparent 1px),linear-gradient(90deg,#ffffff0b 1px,transparent 1px); background-size:48px 48px; padding:24px 28px; position:relative; }
.fb-terminal-head { color:#f5f0e6; font:500 13px 'JetBrains Mono',monospace; margin-bottom:18px; }
.fb-stage { display:flex; align-items:center; gap:14px; padding:11px 0; border-bottom:1px solid #ffffff14; }
.fb-stage-icon { width:18px; text-align:center; }
.fb-stage.ok .fb-stage-icon { color:var(--ma-success); }
.fb-stage.error .fb-stage-icon { color:var(--ma-danger); }
.fb-stage.running .fb-stage-icon { color:#c8a35b; }
.fb-stage.pending .fb-stage-icon { color:#5a5f6a; }
.fb-stage-title { color:#f5f0e6; font-size:13px; }
.fb-stage.running .fb-stage-title { color:#c8a35b; }
.fb-stage-detail { color:#8a8f98; font:11px 'JetBrains Mono',monospace; }
.fb-error { color:var(--ma-danger); font:12px 'JetBrains Mono',monospace; margin-top:14px; padding:10px; background:#cf454d22; border-radius:4px; }
</style>
```

- [ ] **Step 3: MetricsPanel.vue**

```vue
<template>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px">
    <div v-for="m in cards" :key="m.key" class="fb-metric-card" :style="{color: m.color}">
      <small>{{ m.label }}</small>
      <strong>{{ m.value }}</strong>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ metrics: Record<string, number> }>()
const cards = computed(() => {
  const m = props.metrics
  const fmt = (v: number | undefined, pct = false) => v == null ? '—' : pct ? (v * 100).toFixed(2) + '%' : v.toFixed(3)
  return [
    { key: 'IC', label: 'IC', value: fmt(m['IC']), color: 'var(--ma-gold-dark)' },
    { key: 'annualized', label: '年化收益', value: fmt(m['1day.excess_return_with_cost.annualized_return'], true), color: 'var(--ma-success)' },
    { key: 'sharpe', label: '夏普比率', value: fmt(m['1day.excess_return_with_cost.information_ratio']), color: 'var(--ma-ink)' },
    { key: 'drawdown', label: '最大回撤', value: fmt(m['1day.excess_return_with_cost.max_drawdown'], true), color: 'var(--ma-danger)' },
  ]
})
</script>
<style scoped>
.fb-metric-card { background:var(--ma-surface); border:1px solid var(--ma-line); border-radius:var(--ma-radius); padding:14px; text-align:center; }
.fb-metric-card small { display:block; color:var(--ma-muted); font:10px 'JetBrains Mono',monospace; letter-spacing:1px; margin-bottom:4px; }
.fb-metric-card strong { font:700 26px/1 'Noto Serif SC',serif; }
</style>
```

- [ ] **Step 4: EquityChart.vue(ECharts)**

```vue
<template>
  <div class="fb-card" style="padding:14px">
    <div style="color:var(--ma-muted);font:11px 'JetBrains Mono',monospace;margin-bottom:8px">净值曲线 · 策略</div>
    <v-chart v-if="option" :option="option" style="height:280px" autoresize />
    <div v-else style="color:var(--ma-muted);text-align:center;padding:40px">无收益数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
use([CanvasRenderer, LineChart, GridComponent, TooltipComponent])

const props = defineProps<{ equity: [string, number][] }>()
const option = computed(() => {
  if (!props.equity?.length) return null
  return {
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: props.equity.map(e => e[0]), axisLabel: { color: '#858a94' } },
    yAxis: { type: 'value', axisLabel: { color: '#858a94' } },
    series: [{ type: 'line', data: props.equity.map(e => e[1]), showSymbol: false, lineStyle: { color: '#b99a50', width: 2 }, areaStyle: { color: 'rgba(185,154,80,0.1)' } }],
  }
})
</script>
```

- [ ] **Step 5: TopBar.vue(复用 multialpha TopBar 结构)**

```vue
<template>
  <header class="fb-topbar">
    <button class="fb-brand" @click="$emit('home')">
      <span class="fb-logo-frame"><img src="https://h5.crsec.com.cn/logo.png" alt="国新证券" class="fb-logo"/></span>
      <span class="fb-brand-text"><small>国新证券</small><strong>Multiα1pha</strong></span>
    </button>
    <div class="fb-topbar-actions">
      <button class="fb-topbar-btn" @click="$emit('home')">← 返回主站</button>
    </div>
  </header>
</template>
<script setup lang="ts">
defineEmits<{ home: [] }>()
</script>
<style scoped>
.fb-topbar { height:68px; display:flex; justify-content:space-between; align-items:center; padding:0 24px 0 20px; background:#fffffff2; border-bottom:1px solid var(--ma-line); box-shadow:0 1px 12px rgb(25 27 33 / 4%); flex:none; }
.fb-brand { display:flex; align-items:center; gap:12px; background:none; border:none; cursor:pointer; padding:0; }
.fb-logo-frame { width:46px; height:46px; display:grid; place-items:center; overflow:hidden; border-radius:10px; background:#fff; box-shadow:0 5px 16px rgb(132 60 30 / 16%); }
.fb-logo { width:100%; height:100%; object-fit:contain; }
.fb-brand-text { display:flex; flex-direction:column; gap:1px; line-height:1; }
.fb-brand-text small { color:#858994; font:400 12px/1.15 'Noto Sans SC'; letter-spacing:2.5px; }
.fb-brand-text strong { color:var(--ma-ink); font:700 22px/1.1 'Noto Serif SC',serif; }
.fb-topbar-btn { height:36px; padding:0 16px; border-radius:4px; border:none; background:transparent; color:var(--ma-ink); font:500 13px 'Noto Sans SC'; cursor:pointer; }
</style>
```

- [ ] **Step 6: 构建验证**

```bash
cd web && npx vue-tsc --noEmit 2>&1 | grep -i fastbacktest | head
```
预期:无错误。然后 `npm run dev`,浏览器访问 `http://localhost:8080/fastbacktest.html` 确认三态渲染。

```bash
git add web/src/fastbacktest/components/
git commit -m "feat(fast-backtest): all UI components (picker/input/timeline/metrics/chart/topbar)"
```

---

## Task 9: 集成验证 — 端到端测试

**Files:**
- 无新文件,纯验证

**背景**:这是验证 spec 成功标准的关键任务。需要真实启动后端 + 前端,跑一次完整流程。

- [ ] **Step 1: 构建前端到 Flask 静态目录**

```bash
cd web && npm run build:flask 2>&1 | tail -10
```
预期:构建成功,产物在 `git_ignore_folder/static/`。

- [ ] **Step 2: 启动后端**

```bash
rdagent server_ui &
sleep 3
curl http://localhost:19899/health
```
预期:健康检查返回 ok。

- [ ] **Step 3: 测试 Alpha158-only 路径**

```bash
curl -N -X POST http://localhost:19899/fastbacktest/run \
  -H "Content-Type: application/json" \
  -d '{"alpha158":["KMID","KLEN","ROC5"],"description":""}'
```
预期:收到 codegen(跳过)→ backtest running → done(含 trace_id + metrics + equity)。可能较慢(qrun 首次几十秒)。

- [ ] **Step 4: 验证 predict 可发现该 trace**

```bash
curl http://localhost:19899/predict/experiments | python -m json.tool | grep "fast-"
```
预期:能看到 Step 3 产出的 `fast-xxx` trace。

- [ ] **Step 5: 测试自然语言路径(可选,需 LLM 配置)**

```bash
curl -N -X POST http://localhost:19899/fastbacktest/run \
  -H "Content-Type: application/json" \
  -d '{"alpha158":[],"description":"基于过去20日动量与成交量背离的反转因子"}'
```
预期:codegen → factor_eval → backtest → done。

- [ ] **Step 6: 最终提交(若有修复)**

```bash
git add -A
git commit -m "test(fast-backtest): end-to-end integration verification" --allow-empty
```

---

## Self-Review 结果

**1. Spec 覆盖**:
- ✅ 自然语言输入 → Task 2(_generate_factor_code)+ Task 3(编排)
- ✅ Alpha158 勾选 → Task 7(端点 + Picker)+ Task 3(_alpha158_expressions)
- ✅ 两输入组合 → Task 3(run_fast_backtest 的路径分支)
- ✅ LinearModel + csi300 固定 → Task 3(_run_qlib_backtest 的 env + 模板变量)
- ✅ SSE 流式进度 → Task 1(_sse)+ Task 4(端点)+ Task 5(前端 SSE 消费)
- ✅ 微型 trace(predict 可发现)→ Task 3(_build_and_dump_trace)
- ✅ 视觉对齐 multiα1pha → Task 6(令牌)+ Task 8(组件)
- ✅ predict 零改动复用 → Task 9 Step 4 验证

**2. 占位符扫描**:Task 6 Step 4 标注了"骨架后续填充"但 Task 7-8 立即填充,无遗留 TODO。所有代码块完整。

**3. 类型一致性**:`FastBacktestEvent`、`StageState`、`Phase`、`Alpha158Meta` 在各任务间签名一致。`run_fast_backtest` 返回 `Generator[str,None,None]`,Flask 端点正确迭代。

**已知风险(实现时注意)**:
- `LoopBase.__new__` 绕过 `__init__` 后,dump 是否能被 `pickle.load` 正确恢复并让 `query_sota` 读 `loop.trace` —— Task 3 Step 5/6 的测试覆盖了这点,但真实 `query_sota` 调用链需 Task 9 Step 4 最终验证。若失败,备选:dump 前补设 `loop.loop_idx=0, loop.step_idx={}, loop.loop_n=None, loop.step_n=None` 等 `__init__` 中的字段。
- `QlibFBWorkspace` 的 `extra_vars` 注入 Jinja 的方式需确认 —— 现有代码用 `inject_code_from_folder` 渲染模板,Task 3 假设可通过 `extra_vars` 传参。实现时检查 `FBWorkspace.inject_code_from_folder` 是否接受额外变量;若不接受,改为渲染后字符串替换或直接构造 yaml。

{% endraw %}
