import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline
import server


class RestartContracts(unittest.TestCase):
    def request(self):
        return {
            "mode": "e11-a",
            "repo": str(pipeline.ROOT / "data" / "restart-test"),
            "base": "a" * 40,
            "target": "b" * 40,
        }

    def test_completed_job_stays_idempotent_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "jobs"
            request = self.request()
            first = server.Store(root)
            with first.pool:
                with patch.object(first.pool, "submit"):
                    job = first.submit(request, "completed-key")
                with patch.object(server, "execute", return_value={
                    "status": "SUCCEEDED", "trace_id": "trace-restart-test"
                }):
                    first.work(job["job_id"], request)

            restored = server.Store(root)
            with restored.pool:
                with patch.object(restored.pool, "submit") as schedule:
                    result = restored.submit(request, "completed-key")
                    self.assertEqual(result["job_id"], job["job_id"])
                    self.assertEqual(result["status"], "SUCCEEDED")
                    self.assertEqual(result["trace_id"], "trace-restart-test")
                    changed = dict(request, target="c" * 40)
                    with self.assertRaisesRegex(ValueError, "IDEMPOTENCY_CONFLICT"):
                        restored.submit(changed, "completed-key")
                    schedule.assert_not_called()

    def test_unfinished_jobs_require_new_key_after_restart(self):
        for running in (False, True):
            with self.subTest(running=running), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "jobs"
                request = self.request()
                first = server.Store(root)
                with first.pool:
                    with patch.object(first.pool, "submit"):
                        job = first.submit(request, "unfinished-key")
                    if running:
                        with patch.object(server, "execute", side_effect=KeyboardInterrupt):
                            with self.assertRaises(KeyboardInterrupt):
                                first.work(job["job_id"], request)

                restored = server.Store(root)
                with restored.pool:
                    with patch.object(restored.pool, "submit") as schedule:
                        result = restored.submit(request, "unfinished-key")
                        self.assertEqual(result["job_id"], job["job_id"])
                        self.assertEqual(result["status"], "FAILED")
                        self.assertEqual(result["error"]["code"], "SERVER_RESTARTED")
                        saved = json.loads((root / job["job_id"] / "state.json").read_text())
                        self.assertEqual(saved["error"]["code"], "SERVER_RESTARTED")
                        schedule.assert_not_called()
                        retry = restored.submit(request, "retry-key")
                        self.assertNotEqual(retry["job_id"], job["job_id"])
                        self.assertEqual(retry["status"], "QUEUED")
                        schedule.assert_called_once()


if __name__ == "__main__":
    unittest.main()
