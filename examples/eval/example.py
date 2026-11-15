"""Verify frozen task materials or copy one initial workspace; never run an Agent."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import sys


DEFAULT_SUITE = Path(__file__).resolve().parent / "formal20"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def child(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not name or "\\" in name or relative.is_absolute() or any(
        part in ("..", ".") or ":" in part for part in relative.parts
    ):
        raise ValueError(f"Invalid relative path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes suite: {name}")
    return path


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify(suite: Path = DEFAULT_SUITE) -> list[dict]:
    suite = suite.resolve()
    manifest = read_json(suite / "manifest.json")
    if manifest.get("schema_version") != 1 or manifest.get("algorithm") != "sha256":
        raise ValueError("Unsupported manifest")
    expected = manifest["files"]
    for path in suite.rglob("*"):
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError(f"Linked fixture is not supported: {path.relative_to(suite)}")
    actual = {
        path.relative_to(suite).as_posix()
        for path in suite.rglob("*")
        if path.is_file() and path != suite / "manifest.json"
    }
    if actual != set(expected):
        raise ValueError(
            f"File list differs: missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )
    for name, value in expected.items():
        if digest(child(suite, name)) != value:
            raise ValueError(f"SHA256 mismatch: {name}")
    metadata = read_json(suite / "suite.json")
    cases = read_json(child(suite, metadata["cases"]))
    expected_ids = {f"U{i:02}" for i in range(1, 6)} | {
        f"C{i:02}" for i in range(1, 6)
    } | {f"O{i:02}" for i in range(1, 11)}
    if len(cases) != metadata["case_count"] or {case["id"] for case in cases} != expected_ids:
        raise ValueError("Expected the 20 distinct example cases")
    for case in cases:
        if not case["turns"] or not all(isinstance(t, str) and t for t in case["turns"]):
            raise ValueError(f"Missing task turns: {case['id']}")
        for key in ("workspace", "judge_only", "task_file"):
            if not child(suite, case[key]).exists():
                raise ValueError(f"Missing {key}: {case['id']}")
        workspace = child(suite, case["workspace"])
        inputs = {
            p.relative_to(workspace).as_posix(): digest(p)
            for p in workspace.rglob("*") if p.is_file()
        }
        if inputs != case["input_hashes"]:
            raise ValueError(f"Input hashes differ: {case['id']}")
    return cases


def prepare(case_id: str, out: Path, suite: Path = DEFAULT_SUITE) -> Path:
    cases = verify(suite)
    case = next((item for item in cases if item["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    out = out.resolve()
    if out.exists():
        raise ValueError(f"Output already exists: {out}")
    if out.is_relative_to(suite.resolve()):
        raise ValueError("Output must be outside the frozen suite")
    out.mkdir(parents=True)
    workspace = out / "workspace"
    shutil.copytree(child(suite.resolve(), case["workspace"]), workspace)
    # Operator instructions and future turns stay outside the Agent's workspace.
    task = {key: value for key, value in case.items() if key not in (
        "input_hashes", "source_input_hashes", "judge_only", "workspace", "task_file"
    )}
    task["workspace"] = "workspace"
    task["delivery"] = "Send turns sequentially; give the Agent access only to workspace/."
    (out / "task.json").write_text(
        json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="Check files and hashes without executing task code")
    copy = commands.add_parser("prepare", help="Copy only one task's initial input files")
    copy.add_argument("case_id")
    copy.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            cases = verify()
            print(f"Verified {len(cases)} task examples; no Agent or grader was executed.")
        else:
            workspace = prepare(args.case_id, args.out)
            print(f"Initial workspace: {workspace}\nOperator instructions: {workspace.parent / 'task.json'}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Example validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
