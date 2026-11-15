"""Offline packaging tests, independent of task code and evaluation scorers."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("eval_example", Path(__file__).with_name("example.py"))
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class ExampleTests(unittest.TestCase):
    def test_all_twenty_materials_are_intact(self):
        self.assertEqual(len(example.verify()), 20)

    def test_prepare_preserves_bytes_and_excludes_judge_materials(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "C02"
            workspace = example.prepare("C02", out)
            source = example.DEFAULT_SUITE / "cases/C02/input"
            original = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            copied = {p.relative_to(workspace): p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
            self.assertEqual(copied, original)
            self.assertEqual({p.name for p in out.iterdir()}, {"workspace", "task.json"})
            self.assertNotIn("task.json", {p.name for p in workspace.iterdir()})
            with self.assertRaisesRegex(ValueError, "already exists"):
                example.prepare("C02", out)

    def test_tampering_is_rejected_before_prepare(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = Path(temp) / "suite"
            shutil.copytree(example.DEFAULT_SUITE, suite)
            target = next((suite / "cases/C02/input").rglob("*.conf"))
            target.write_bytes(target.read_bytes() + b"\nchanged")
            out = Path(temp) / "run"
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                example.prepare("C02", out, suite)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
