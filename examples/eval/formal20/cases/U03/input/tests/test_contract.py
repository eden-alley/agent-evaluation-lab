import asyncio
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_asyncio import LocalEventLoop
runtime_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
os.environ["DEEPTUTOR_HOME"] = runtime_dir.name
os.environ["DEEPTUTOR_WORKSPACE_ROOT"] = runtime_dir.name
os.environ.pop("DEEPTUTOR_WORKSPACE_ALLOWED_ROOTS", None)
from deeptutor.app.service import TurnApplicationService
from deeptutor.runtime.coordination import MemoryCoordinator
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def tearDownModule():
    runtime_dir.cleanup()


class WaitingTurnRecovery(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(loop_factory=LocalEventLoop)

    async def asyncSetUp(self):
        db = tempfile.TemporaryDirectory(dir=runtime_dir.name)
        self.addCleanup(db.cleanup)
        self.store = SQLiteSessionStore(Path(db.name) / "history.sqlite3")
        self.coordinator = MemoryCoordinator(lease_ttl_seconds=60)
        self.app = TurnApplicationService(
            SimpleNamespace(get=lambda: self.store),
            SimpleNamespace(get=lambda _store: None),
            self.coordinator,
        )
        self.session = await self.store.create_session(title="Local test")
        self.turn = await self.store.begin_turn(self.session["id"], "chat")
        self.turn_id = self.turn["id"]

    async def wait(self):
        await self.store.update_turn_status(self.turn_id, "waiting_input")

    async def test_missing_worker_unblocks_same_session(self):
        await self.wait()
        self.assertFalse(await self.app.submit_user_reply(self.turn_id, text="continue"))
        current = await self.store.get_turn(self.turn_id)
        self.assertEqual(current["status"], "failed")
        self.assertEqual(current["failure_code"], "worker_lost")
        self.assertTrue(current["retryable"])
        fresh = await self.store.begin_turn(self.session["id"], "chat")
        self.assertNotEqual(fresh["id"], self.turn_id)

