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

    def test_disjoint_complete_pages_with_tied_timestamps(self):
        first = self.fetch(limit=20)
        second = self.fetch(limit=20, offset=20)
        last = self.fetch(limit=20, offset=40)
        self.assertEqual([len(first), len(second), len(last)], [20, 20, 5])
        self.assertEqual(first + second + last, self.expected)

    def test_empty_page_and_validation(self):
        self.assertEqual(self.fetch(limit=20, offset=45), [])
        self.assertEqual(self.fetch(limit=100), self.expected)
        for query in ({"limit": 0}, {"limit": 101}, {"limit": "x"}, {"limit": "1.5"},
                      {"limit": 2, "offset": -1}, {"limit": 2, "offset": "x"},
                      {"offset": 0}):
            with self.subTest(query=query):
                response = self.client.get("/api/v1/projects", params=query)
                self.assertEqual(response.status_code, 422)

    def test_single_project_and_create_still_work(self):
        first = self.expected[0]
        self.assertEqual(self.client.get("/api/v1/projects/" + first["id"]).json(), first)
        created = self.client.post("/api/v1/projects", json={"name": "A new project"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.get("/api/v1/projects/" + created.json()["id"]).json(), created.json())
