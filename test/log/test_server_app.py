"""Bug 1 回归测试：/traces 列表应合并内存 catalog 中尚未落盘的 running 任务。

根因：_collect_existing_trace_ids 只扫文件系统（需 .pkl），而 /upload 后新任务
仅在内存 trace_states（status=running），子进程写出首个 .pkl 有数秒延迟，
导致 createTask 后 loadTraceIds 拉不到新任务 → 任务看板为空。

修复后：合并文件系统扫描结果与 trace_states 中 running 的任务，去重排序。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rdagent.log.server import app as server_app


class CollectExistingTraceIdsTestCase(unittest.TestCase):
    """测试 _collect_existing_trace_ids 的文件系统扫描 + 内存 catalog 合并行为。"""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.trace_root = Path(self._tmp_dir.name)
        # 保存原始 trace_states，测试间隔离
        self._orig_trace_states = server_app.trace_states.copy()
        server_app.trace_states.clear()

    def tearDown(self) -> None:
        server_app.trace_states.clear()
        server_app.trace_states.update(self._orig_trace_states)
        self._tmp_dir.cleanup()

    def _make_persisted_trace(self, scenario: str, name: str) -> str:
        """在文件系统创建一个已落盘的 trace（含 .pkl）。"""
        trace_dir = self.trace_root / scenario / name
        trace_dir.mkdir(parents=True)
        (trace_dir / "trace.12345.pkl").write_bytes(b"\x80\x04\x95\x05\x00\x00\x00")
        return f"{scenario}/{name}"

    def _add_running_catalog_entry(self, trace_id: str) -> None:
        """在内存 trace_states 注入一个 running 状态的任务（模拟 /upload 后未落盘）。"""
        server_app.trace_states[trace_id] = {
            "status": "running",
            "loops": set(),
            "created_at": "2026-07-27T00:00:00+00:00",
            "updated_at": None,
            "has_chart": False,
            "_tags_seen": set(),
        }

    # ---- 场景 1：刚上传、子进程未落盘 → 必须出现在列表（Bug 1 核心）----
    def test_running_task_in_catalog_appears_even_without_pkl(self) -> None:
        trace_id = "Finance Data Building/plain-transformation"
        self._add_running_catalog_entry(trace_id)
        # 文件系统中该任务目录不存在（无 .pkl）

        ids = server_app._collect_existing_trace_ids(self.trace_root)

        self.assertIn(trace_id, ids)

    # ---- 场景 2：已落盘的历史任务（回归保护）----
    def test_persisted_task_with_pkl_still_listed(self) -> None:
        persisted = self._make_persisted_trace("Finance Data Building", "minty-hook")

        ids = server_app._collect_existing_trace_ids(self.trace_root)

        self.assertEqual(ids, [persisted])

    # ---- 场景 3：文件系统与内存并存 → 去重合并 ----
    def test_merges_filesystem_and_running_catalog_without_duplicates(self) -> None:
        persisted = self._make_persisted_trace("Finance Data Building", "alpha-done")
        running = "Finance Whole Pipeline/jet-investor"
        self._add_running_catalog_entry(running)

        ids = server_app._collect_existing_trace_ids(self.trace_root)

        self.assertEqual(sorted(ids), sorted([persisted, running]))

    # ---- 场景 4：已完成任务同时在 fs 和 catalog → 不重复 ----
    def test_done_task_in_catalog_not_duplicated(self) -> None:
        done_id = self._make_persisted_trace("Finance Model Implementation", "model-x")
        # 同一任务在 catalog 中标记为 done
        server_app.trace_states[done_id] = {
            "status": "done",
            "loops": {0, 1},
            "created_at": "2026-07-27T00:00:00+00:00",
            "updated_at": "2026-07-27T01:00:00+00:00",
            "has_chart": False,
            "_tags_seen": {"END"},
        }

        ids = server_app._collect_existing_trace_ids(self.trace_root)

        self.assertEqual(ids, [done_id])

    # ---- 场景 5：trace_root 不存在但 catalog 有 running → 仍返回 ----
    def test_running_catalog_returned_even_when_root_missing(self) -> None:
        missing_root = self.trace_root / "nonexistent"
        running = "Finance Data Building/plain-transformation"
        self._add_running_catalog_entry(running)

        ids = server_app._collect_existing_trace_ids(missing_root)

        self.assertIn(running, ids)


if __name__ == "__main__":
    unittest.main()
