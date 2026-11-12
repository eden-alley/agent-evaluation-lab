"""Prepare, reset and validate the frozen U02 Windows task environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
RUNTIME = WORK / "runtime"
WORKSPACE = WORK / "workspace"
PYTHON = RUNTIME / "Scripts" / "python.exe"
EVIDENCE = WORK / "evidence"


def hashes(folder):
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*")) if path.is_file()
    }


def verify_materials():
    manifest = json.loads((ROOT / "task.json").read_text(encoding="utf-8"))
    if hashes(ROOT / "seed") != manifest["initial_files"]:
        raise RuntimeError("Frozen seed files changed.")
    for name, expected in manifest["material_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Frozen material changed: {name}")
    return manifest


def remove_managed(folder):
    # All destructive operations are restricted to these two owned directories.
    if folder not in (RUNTIME, WORKSPACE):
        raise RuntimeError("Unmanaged removal target.")
    if WORK.is_symlink() or WORK.is_junction() or folder.is_symlink() or folder.is_junction():
        raise RuntimeError("Refusing to remove a redirected work directory.")
    if folder.resolve().parent != WORK.resolve():
        raise RuntimeError("Removal target escaped the task work directory.")
    if folder.exists():
        shutil.rmtree(folder)


def run(command, cwd, log):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(item) for item in command], cwd=cwd, capture_output=True,
        encoding="utf-8", errors="replace", timeout=300,
        env={**os.environ, "PYTHONUTF8": "1", "LANGSMITH_TRACING": "false"},
    )
    (EVIDENCE / log).write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def require_runtime():
    ready = RUNTIME / "ready.json"
    if not ready.is_file():
        raise RuntimeError("Run prepare successfully before using this environment.")
    saved = json.loads(ready.read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256((ROOT / "requirements.lock").read_bytes()).hexdigest()
    if saved["requirements_sha256"] != fingerprint:
        raise RuntimeError("Dependencies changed; prepare the environment again.")
    return saved


def reset():
    verify_materials()
    remove_managed(WORKSPACE)
    shutil.copytree(ROOT / "seed", WORKSPACE)
    if hashes(WORKSPACE) != hashes(ROOT / "seed"):
        raise RuntimeError("Reset failed to reproduce the initial files.")


def prepare(wheelhouse):
    verify_materials()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Prepare requires Windows and Python 3.12.")
    WORK.mkdir(parents=True, exist_ok=True)
    remove_managed(RUNTIME)
    venv.EnvBuilder(with_pip=True).create(RUNTIME)
    command = [PYTHON, "-B", "-I", "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--require-hashes", "-r", ROOT / "requirements.lock"]
    if wheelhouse:
        command.extend(["--no-index", "--find-links", Path(wheelhouse).resolve()])
    else:
        command.extend(["--index-url", "https://pypi.org/simple"])
    result = run(command, ROOT, "install.txt")
    if result.returncode:
        raise RuntimeError("Dependency installation failed; see work/evidence/install.txt.")
    result = run([PYTHON, "-B", "-I", "-m", "pip", "check"], ROOT, "pip-check.txt")
    if result.returncode:
        raise RuntimeError("Dependency consistency check failed.")
    result = run([PYTHON, "-B", "-I", "-m", "pip", "freeze"], ROOT, "pip-freeze.txt")
    expected = {
        line.split(" --hash=", 1)[0].lower().replace("_", "-")
        for line in (ROOT / "requirements.lock").read_text().splitlines()
    }
    installed = {line.lower().replace("_", "-") for line in result.stdout.splitlines()}
    if result.returncode or installed != expected:
        raise RuntimeError("Installed packages differ from the dependency lock.")
    metadata = {
        "python": sys.version.split()[0], "platform": sys.platform,
        "requirements_sha256": hashlib.sha256((ROOT / "requirements.lock").read_bytes()).hexdigest(),
        "packages": sorted(installed),
    }
    (RUNTIME / "ready.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    reset()
    print(json.dumps(metadata, indent=2))


def independent(candidate, label):
    output = EVIDENCE / f"{label}.json"
    output.unlink(missing_ok=True)
    result = run(
        [PYTHON, "-B", "-I", ROOT / "evaluator/check.py", candidate, output],
        candidate, f"{label}.txt",
    )
    if result.returncode not in (0, 1) or not output.is_file():
        raise RuntimeError(f"Independent acceptance could not run: {label}")
    report = json.loads(output.read_text(encoding="utf-8"))
    if report["tests"] != 5 or report["success"] != (result.returncode == 0):
        raise RuntimeError("Independent acceptance result is incomplete.")
    return report


def grade():
    manifest = verify_materials()
    require_runtime()
    result = independent(WORKSPACE, "candidate")
    current = hashes(WORKSPACE)
    initial = manifest["initial_files"]
    changed = {
        name for name in set(initial) | set(current)
        if initial.get(name) != current.get(name)
    }
    extra = sorted(changed - set(manifest["allowed_changes"]))
    result["out_of_scope"] = extra
    result["report_present"] = (WORKSPACE / "report.md").is_file()
    result["automatic_checks_passed"] = result["success"] and not extra and result["report_present"]
    result["report_content_review"] = "required"
    (EVIDENCE / "grade.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["automatic_checks_passed"] else 1


def validate():
    manifest = verify_materials()
    runtime = require_runtime()
    expected = {"original": (1, 3), "reference": (0, 5), "over_trim": (0, 4)}
    reports = {}
    try:
        for name, (public_exit, passed) in expected.items():
            reset()
            if name != "original":
                shutil.copyfile(ROOT / "evaluator/reference-character.py",
                                WORKSPACE / "src/langchain_text_splitters/character.py")
            if name == "over_trim":
                path = WORKSPACE / "src/langchain_text_splitters/character.py"
                source = path.read_text(encoding="utf-8")
                before = "piece = s.strip() if self._strip_whitespace else s"
                if source.count(before) != 1:
                    raise RuntimeError("Could not construct the over-trimming control.")
                path.write_text(source.replace(before, "piece = s.strip()"), encoding="utf-8")
            public = run([PYTHON, "-B", "-I", WORKSPACE / "run-tests.py"],
                         WORKSPACE, f"{name}-public.txt")
            report = independent(WORKSPACE, name)
            report["public_exit"] = public.returncode
            if public.returncode != public_exit or report["passed"] != passed:
                raise RuntimeError(f"Unexpected behavior in the {name} control.")
            reports[name] = report
        if reports["over_trim"]["checks"]["test_retains_whitespace_when_disabled"]:
            raise RuntimeError("Acceptance missed the over-trimming regression.")
        (WORKSPACE / "temporary.txt").write_text("reset probe", encoding="utf-8")
    finally:
        reset()
    reset_matches = hashes(WORKSPACE) == manifest["initial_files"]
    if not reset_matches:
        raise RuntimeError("Reset did not restore the frozen defect.")
    summary = {
        "task": "U02", "environment_verified": True, "model_requests": 0,
        "runtime": runtime, "controls": reports, "reset_matches_initial": reset_matches,
        "source_files_checked": len(manifest["initial_files"]),
    }
    (EVIDENCE / "validation.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "reset", "grade", "validate"))
    parser.add_argument("--wheelhouse", help="Install locked wheels from a local directory.")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.wheelhouse)
    elif args.command == "reset":
        reset()
        print("Initial workspace restored and hashes verified.")
    elif args.command == "grade":
        return grade()
    else:
        validate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
