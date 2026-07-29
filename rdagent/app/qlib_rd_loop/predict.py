"""
predict.py — T+1 预测入口(宿主端)

经 RDAgentTask spawn,负责:
1. 把 SOTA 因子代码写到 workspace 临时目录
2. 启动 docker 挂载 workspace + qlib data
3. 容器内跑 predict_infer.py(五步 pipeline)
4. 从 stdout 拿 Top20 JSON
5. 推前端 + 写历史记录
"""
import json
import tempfile
from pathlib import Path

from rdagent.log import rdagent_logger as logger
from rdagent.utils.env import QTDockerEnv


def main(trace_id: str, workspace_path: str, sota_factors: list):
    """T+1 预测入口。

    Args:
        trace_id: SOTA 实验 trace id(如 "Finance Data Building/baked-yeast")
        workspace_path: SOTA workspace 绝对路径
        sota_factors: [(factor_name, factor_code), ...] 从 query_sota 取的因子列表
    """
    logger.info(f"预测任务启动: trace_id={trace_id}")

    # 1. 把因子代码写到 workspace 临时目录
    factors_dir = Path(workspace_path) / "_predict_factors"
    factors_dir.mkdir(exist_ok=True)
    for fname, code in sota_factors:
        (factors_dir / f"{fname}.py").write_text(code)
    logger.info(f"写入 {len(sota_factors)} 个因子代码到 {factors_dir}")

    # 2. 准备 predict_infer.py(从模板目录复制)
    # predict.py = rdagent/app/qlib_rd_loop/predict.py → rdagent/scenarios/...
    template_dir = Path(__file__).resolve().parent.parent.parent / "scenarios" / "qlib" / "experiment" / "factor_template"
    infer_script = template_dir / "predict_infer.py"
    if not infer_script.exists():
        raise FileNotFoundError(f"predict_infer.py not found at {infer_script}")
    # 复制到 workspace
    ws_infer = Path(workspace_path) / "predict_infer.py"
    ws_infer.write_text(infer_script.read_text())

    # 3. 启动 docker 跑 predict_infer.py
    logger.info("启动 docker 执行预测...")
    env = QTDockerEnv()
    env.prepare()

    # docker 挂载: workspace → /workspace/qlib_workspace, qlib data → /root/.qlib
    # extra_volumes 由 QTDockerEnv 自动处理(~/.qlib → /root/.qlib)
    execute_log = env.check_output(
        local_path=str(workspace_path),
        entry=f"python predict_infer.py --workspace /workspace/qlib_workspace --factors-dir /workspace/qlib_workspace/_predict_factors",
    )

    # 4. 从 stdout 解析 Top20 JSON
    output_text = execute_log if isinstance(execute_log, str) else execute_log.decode("utf-8", errors="replace")

    # 找 JSON 行(=== JSON === 标记后)
    result = None
    json_marker = "=== JSON ==="
    if json_marker in output_text:
        json_part = output_text[output_text.index(json_marker) + len(json_marker):].strip()
        # 取第一行完整 JSON
        json_line = json_part.split("\n")[0].strip()
        try:
            result = json.loads(json_line)
        except json.JSONDecodeError:
            logger.error(f"JSON 解析失败: {json_line[:200]}")
    elif output_text.strip().startswith("{"):
        try:
            result = json.loads(output_text.strip().split("\n")[-1])
        except json.JSONDecodeError:
            pass

    if result is None:
        logger.error("未能从 docker 输出解析预测结果")
        logger.info(f"docker stdout:\n{output_text[-500:]}")
        raise RuntimeError("预测结果解析失败")

    logger.info(f"预测完成: 日期={result.get('predict_date')}, Top20 数={len(result.get('top20', []))}")

    # 5. 推前端
    logger.log_object(result, tag="prediction.top20")

    # 6. 写历史记录
    _write_history(trace_id, result)

    # 7. 清理临时文件
    import shutil

    shutil.rmtree(factors_dir, ignore_errors=True)
    ws_infer.unlink(missing_ok=True)

    return result


def _write_history(trace_id: str, result: dict):
    """写历史预测记录到 JSON 文件"""
    from datetime import datetime

    from rdagent.log.ui.conf import UI_SETTING

    history_dir = Path(UI_SETTING.trace_folder) / "Prediction History"
    history_dir.mkdir(parents=True, exist_ok=True)

    date_str = result.get("predict_date", datetime.now().strftime("%Y-%m-%d"))
    trace_short = trace_id.split("/")[-1][:20]
    filename = f"{trace_short}-{date_str}.json"
    filepath = history_dir / filename

    record = {
        "date": date_str,
        "source_trace_id": trace_id,
        "top20": result.get("top20", []),
        "created_at": datetime.now().isoformat(),
    }
    filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    logger.info(f"历史记录写入: {filepath}")
