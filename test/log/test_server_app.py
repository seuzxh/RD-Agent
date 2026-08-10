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
from types import SimpleNamespace
from unittest import mock

from rdagent.log.server import app as server_app
from rdagent.log.server.task_state import create_task_state, read_task_state, update_task_state


class SotaFromMessagesTestCase(unittest.TestCase):
    """测试 _sota_from_messages 正确识别最后一个被采纳（decision=True）的 loop。"""

    def _make_message(self, loop_id, tag, content):
        return {"loop_id": loop_id, "tag": tag, "content": content}

    def _loop_messages(self, loop_id, decision):
        """生成一轮完整的消息流，feedback.hypothesis_feedback 的 decision 可控。"""
        return [
            self._make_message(loop_id, "research.hypothesis", {"hypothesis": f"h{loop_id}"}),
            self._make_message(loop_id, "research.tasks", [{"name": f"factor_{loop_id}"}]),
            self._make_message(loop_id, "evolving.codes", [{"target_task_name": f"factor_{loop_id}", "workspace": {"factor.py": f"code_{loop_id}"}}]),
            self._make_message(loop_id, "feedback.metric", {"result": json.dumps({"IC": 0.01 * (loop_id + 1)})}),
            self._make_message(loop_id, "feedback.hypothesis_feedback", {"decision": decision, "reason": f"r{loop_id}"}),
        ]

    def test_single_accepted_loop(self):
        messages = self._loop_messages(0, True)
        result = server_app._sota_from_messages(messages)
        self.assertNotIn("error", result)
        self.assertEqual(result["sota_loop_id"], 0)
        self.assertEqual(result["sota_hypothesis"], {"hypothesis": "h0"})
        self.assertEqual(result["sota_feedback"], {"decision": True, "reason": "r0"})
        self.assertEqual(result["sota_metrics"], {"IC": 0.01})
        self.assertEqual(len(result["sota_factors"]), 1)
        self.assertEqual(result["sota_factors"][0]["name"], "factor_0")

    def test_last_accepted_loop_becomes_sota(self):
        # Loop 0 accepted, loop 1 rejected, loop 2 accepted -> SOTA should be loop 2
        messages = []
        for loop_id, decision in [(0, True), (1, False), (2, True)]:
            messages.extend(self._loop_messages(loop_id, decision))
        result = server_app._sota_from_messages(messages)
        self.assertNotIn("error", result)
        self.assertEqual(result["sota_loop_id"], 2)
        self.assertEqual(result["sota_hypothesis"], {"hypothesis": "h2"})
        self.assertEqual(result["sota_metrics"], {"IC": 0.03})
        self.assertEqual(result["sota_factors"][0]["name"], "factor_2")

    def test_rejected_last_loop_does_not_overwrite_sota(self):
        # hot-clause 场景：loop 7 accepted，loop 8 rejected -> SOTA 应为 loop 7
        messages = []
        for loop_id in range(9):
            decision = loop_id == 7
            messages.extend(self._loop_messages(loop_id, decision))
        result = server_app._sota_from_messages(messages)
        self.assertNotIn("error", result)
        self.assertEqual(result["sota_loop_id"], 7)
        self.assertEqual(result["sota_hypothesis"], {"hypothesis": "h7"})

    def test_all_rejected_returns_error(self):
        messages = []
        for loop_id in range(3):
            messages.extend(self._loop_messages(loop_id, False))
        result = server_app._sota_from_messages(messages)
        self.assertIn("error", result)

    def test_no_feedback_returns_error(self):
        messages = [
            self._make_message(0, "research.hypothesis", {"hypothesis": "h0"}),
            self._make_message(0, "feedback.metric", {"result": json.dumps({"IC": 0.01})}),
        ]
        result = server_app._sota_from_messages(messages)
        self.assertIn("error", result)


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

    def test_task_state_without_pickle_is_listed(self) -> None:
        trace_dir = self.trace_root / "Finance Data Building" / "starting-task"
        create_task_state(
            trace_dir,
            task_id="Finance Data Building/starting-task",
            scenario="Finance Data Building",
            server_instance_id="server-a",
            server_pid=100,
            requested_loops=3,
            task_token="token-a",
        )

        ids = server_app._collect_existing_trace_ids(self.trace_root)

        self.assertIn("Finance Data Building/starting-task", ids)


class TaskLifecycleStateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.trace_dir = Path(self._tmp_dir.name) / "Finance Data Building" / "task-a"
        self.trace_id = "Finance Data Building/task-a"
        self._orig_trace_states = server_app.trace_states.copy()
        server_app.trace_states.clear()

    def tearDown(self) -> None:
        server_app.trace_states.clear()
        server_app.trace_states.update(self._orig_trace_states)
        self._tmp_dir.cleanup()

    def _create_state(self):
        return create_task_state(
            self.trace_dir,
            task_id=self.trace_id,
            scenario="Finance Data Building",
            server_instance_id="server-a",
            server_pid=100,
            requested_loops=3,
            task_token="token-a",
        )

    def test_loop_feedback_does_not_finish_task(self) -> None:
        for tag in ("research.hypothesis", "feedback.metric", "feedback.hypothesis_feedback"):
            server_app._update_trace_state(
                self.trace_id,
                {"tag": tag, "loop_id": 0, "content": {"decision": False}},
            )

        self.assertEqual(server_app.trace_states[self.trace_id]["status"], "running")

    def test_end_code_controls_terminal_status(self) -> None:
        server_app._update_trace_state(self.trace_id, {"tag": "END", "content": {"end_code": 0}})
        self.assertEqual(server_app.trace_states[self.trace_id]["status"], "done")

        server_app.trace_states.clear()
        server_app._update_trace_state(self.trace_id, {"tag": "END", "content": {"end_code": -1}})
        self.assertEqual(server_app.trace_states[self.trace_id]["status"], "error")

    def test_no_sota_with_zero_exit_is_done(self) -> None:
        self._create_state()
        task = SimpleNamespace(
            log_trace_path=str(self.trace_dir),
            messages=[{"tag": "feedback.hypothesis_feedback", "content": {"decision": False}}],
            assigned_gpu=None,
        )

        server_app._finalize_task(task, self.trace_id, 0)

        state = read_task_state(self.trace_dir)
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["reason"], "completed")
        self.assertEqual(task.messages[-1]["tag"], "END")

    def test_user_cancel_cannot_be_overwritten_by_watcher(self) -> None:
        self._create_state()
        update_task_state(self.trace_dir, status="error", end_code=-1, reason="user_cancelled")
        task = SimpleNamespace(log_trace_path=str(self.trace_dir), messages=[], assigned_gpu=None)

        server_app._finalize_task(task, self.trace_id, -15)

        state = read_task_state(self.trace_dir)
        self.assertEqual(state["reason"], "user_cancelled")
        self.assertEqual(state["end_code"], -1)

    def test_restart_marks_running_task_error_and_cleans_resources(self) -> None:
        self._create_state()
        update_task_state(self.trace_dir, status="running", worker_pid=123, worker_create_time=456.0)

        with mock.patch.object(server_app, "_terminate_persisted_worker") as terminate, mock.patch.object(
            server_app, "_cleanup_task_containers",
        ) as cleanup:
            server_app._recover_interrupted_tasks(Path(self._tmp_dir.name))

        state = read_task_state(self.trace_dir)
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["reason"], "server_restarted")
        terminate.assert_called_once()
        cleanup.assert_called_once_with("token-a")

    def test_restart_marks_incomplete_state_unknown(self) -> None:
        self.trace_dir.mkdir(parents=True)
        (self.trace_dir / ".task-state.json").write_text(
            json.dumps({"schema_version": 1, "status": "running"}),
            encoding="utf-8",
        )

        server_app._recover_interrupted_tasks(Path(self._tmp_dir.name))

        state = read_task_state(self.trace_dir)
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["reason"], "state_unknown_after_restart")

    def test_pid_create_time_mismatch_is_not_killed(self) -> None:
        process = mock.Mock()
        process.create_time.return_value = 999.0
        with mock.patch.object(server_app.psutil, "Process", return_value=process), mock.patch.object(
            server_app.os, "killpg",
        ) as killpg:
            server_app._terminate_persisted_worker(
                {"worker_pid": 123, "worker_create_time": 456.0, "process_group_id": 123},
            )

        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        killpg.assert_not_called()

    def test_process_bootstrap_failure_is_persisted(self) -> None:
        task = server_app.RDAgentTask(
            target_name="fin_factor",
            kwargs={},
            stdout_path=str(self.trace_dir.with_suffix(".log")),
            log_trace_path=str(self.trace_dir),
            scenario="Finance Data Building",
            trace_name="task-a",
            create_process=False,
            assigned_gpu=2,
        )
        task.process = mock.Mock()
        task.process.start.side_effect = RuntimeError("cannot start")

        with mock.patch.object(server_app, "_release_gpu") as release_gpu, self.assertRaisesRegex(
            RuntimeError, "cannot start"
        ):
            task.start()

        state = read_task_state(self.trace_dir)
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["reason"], "bootstrap_failed")
        self.assertEqual(state["end_code"], -3)
        release_gpu.assert_called_once_with(2)
        task.process = None
        task.stop()

    def test_status_endpoint_keeps_loop_feedback_running(self) -> None:
        self._create_state()
        update_task_state(self.trace_dir, status="running")
        server_app._update_trace_state(
            self.trace_id,
            {"tag": "feedback.hypothesis_feedback", "loop_id": 0, "content": {"decision": False}},
        )

        with mock.patch.object(server_app, "log_folder_path", Path(self._tmp_dir.name)):
            response = server_app.app.test_client().get("/traces/status", query_string={"id": self.trace_id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]["status"], "running")

    def test_legacy_complete_loop_without_end_is_error_after_restart(self) -> None:
        feedback_dir = self.trace_dir / "Loop_0" / "feedback" / "123"
        hypothesis_dir = self.trace_dir / "Loop_0" / "propose" / "hypothesis" / "123"
        feedback_dir.mkdir(parents=True)
        hypothesis_dir.mkdir(parents=True)
        (feedback_dir / "2026-08-11_00-00-00-000001.pkl").write_bytes(b"x")
        (hypothesis_dir / "2026-08-11_00-00-01-000001.pkl").write_bytes(b"x")

        server_app._index_trace_catalog_from_files(self.trace_dir, self.trace_id)

        self.assertEqual(server_app.trace_states[self.trace_id]["status"], "error")


if __name__ == "__main__":
    unittest.main()
