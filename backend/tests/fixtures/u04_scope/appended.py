from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lab.db import connect, initialize
from lab.projects import router
from local_asyncio import LocalEventLoop


class ProjectPagination(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "local.sqlite"
        initialize(self.db)
        self.expected = [
            {"id": f"project-{n:02d}", "name": f"Name {n}", "description": "fixture",
             "created_at": f"2026-11-01T00:00:{n // 4:02d}Z", "updated_at": "2026-11-01T00:00:00Z"}
            for n in range(45)
        ]
        with connect(self.db) as conn:
            conn.executemany(
                "INSERT INTO projects (id,name,description,created_at,updated_at) VALUES (?,?,?,?,?)",
                [tuple(row.values()) for row in reversed(self.expected)],
            )
        app = FastAPI()
        app.state.db_path = self.db
        app.include_router(router)
        self.client = TestClient(app, backend_options={"loop_factory": LocalEventLoop})
        self.addCleanup(self.client.close)

    def fetch(self, **query):
        result = self.client.get("/api/v1/projects", params=query)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(set(result.json()), {"items"})
        return result.json()["items"]

    def test_first_page_and_existing_request(self):
        self.assertEqual(self.fetch(), self.expected)
        self.assertEqual(self.fetch(limit=20), self.expected[:20])

    def test_pages_are_disjoint_and_complete(self):
        pages = [self.fetch(limit=20, offset=offset) for offset in (0, 20, 40, 60)]
        self.assertEqual([len(page) for page in pages], [20, 20, 5, 0])
        seen = [row["id"] for page in pages for row in page]
        self.assertEqual(seen, [row["id"] for row in self.expected])
        self.assertEqual(len(set(seen)), len(seen))

    def test_limit_bounds_and_default_offset(self):
        self.assertEqual(self.fetch(limit=1), self.expected[:1])
        self.assertEqual(self.fetch(limit=100), self.expected)
        self.assertEqual(len(self.fetch(limit=100, offset=0)), 45)
        self.assertEqual(self.fetch(limit=5, offset=43), self.expected[43:])

    def test_invalid_params_return_422(self):
        cases = [
            {"offset": 0}, {"offset": 20},
            {"limit": 0}, {"limit": 101}, {"limit": -1}, {"limit": "abc"},
            {"limit": ""}, {"limit": "2.5"}, {"limit": " 5"},
            {"offset": -1}, {"offset": "x"}, {"limit": 10, "offset": -3},
            {"limit": 10, "offset": ""}, {"limit": True},
        ]
        for params in cases:
            with self.subTest(params=params):
                result = self.client.get("/api/v1/projects", params=params)
                self.assertEqual(result.status_code, 422, result.text)
                self.assertIn("error", result.json())

    def test_pagination_over_empty_and_beyond_end(self):
        with connect(self.db) as conn:
            conn.execute("DELETE FROM projects")
        self.assertEqual(self.fetch(), [])
        self.assertEqual(self.fetch(limit=20), [])
        self.assertEqual(self.fetch(limit=20, offset=100), [])

    def test_single_project_route_unaffected(self):
        result = self.client.get("/api/v1/projects/project-00")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), self.expected[0])
        missing = self.client.get("/api/v1/projects/missing", params={"limit": 20})
        self.assertEqual(missing.status_code, 404)

