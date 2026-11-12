"""Independent Windows MXC adapter. No model client and no host-execution fallback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ASSETS = Path(__file__).with_name("assets")
ENV_NAMES = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC",
             "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
             "HOMEDRIVE", "HOMEPATH", "PROGRAMFILES", "PROGRAMFILES(X86)",
             "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "CODEX_HOME",
             "USERNAME", "USERDOMAIN", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def codex_path():
    for entry in os.get_exec_path():
        path = Path(entry.strip('"'))
        if path.is_absolute() and (path / "codex.exe").is_file():
            return (path / "codex.exe").resolve()
    raise RuntimeError("找不到原生 codex.exe，未执行检查。")

class NativeExecutor:
    def identity(self):
        if os.name != "nt":
            raise RuntimeError("本检查环境要求 Windows 原生沙箱。")
        executable = codex_path()
        return {"backend": "windows-mxc-v1", "python": str(Path(sys.executable).resolve()),
                "python_version": sys.version, "python_sha256": file_digest(sys.executable),
                "sandbox": str(executable), "sandbox_sha256": file_digest(executable)}

    def run(self, workspace, suite):
        identity = self.identity()
        workspace = Path(workspace).resolve(strict=True)
        for executable in (identity["python"], identity["sandbox"]):
            if Path(executable).is_relative_to(workspace):
                raise RuntimeError("检查执行器必须位于交付物工作区之外。")
        trusted = workspace / ".checker"
        trusted.mkdir()
        for name in ("runner.py", suite + ".py"):
            (trusted / name).write_bytes((ASSETS / name).read_bytes())
        script = workspace / ".check-command.cmd"
        script.write_text('@echo off\nchcp 65001 >nul\n"' + identity["python"] +
                          '" -I -B ".checker\\runner.py" ' + suite + '\n', encoding="utf-8", newline="\r\n")
        env = {key: value for key, value in os.environ.items() if key.upper() in ENV_NAMES}
        env["PYTHONIOENCODING"] = "utf-8"
        args = [identity["sandbox"], "sandbox", "-c", "windows.sandbox=mxc", "--include-managed-config",
                "--permission-profile", ":workspace", "-C", str(workspace), "--",
                str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe"), "/d", "/s", "/c", ".\\.check-command.cmd"]
        started = time.monotonic()
        with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
            with subprocess.Popen(args, cwd=workspace, env=env, shell=False, stdin=subprocess.DEVNULL,
                                  stdout=out_file, stderr=err_file) as proc:
                try:
                    proc.wait(timeout=60)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    try:
                        subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                                        "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                    finally:
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait()
                    raise
            if out_file.tell() + err_file.tell() > 4 * 1024 * 1024:
                raise RuntimeError("检查输出超过上限，未产生任务成绩。")
            out_file.seek(0); err_file.seek(0)
            stdout, stderr = out_file.read(), err_file.read()
        out, err = stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        lines = [line for line in out.splitlines() if line.startswith("CHECK_RESULT=")]
        if len(lines) != 1:
            raise RuntimeError("检查没有返回有效测试结果；请查看原生沙箱是否可用。")
        return {**json.loads(lines[0].split("=", 1)[1]), "suite": suite, "exit_code": proc.returncode,
                "stdout": out, "stderr": err, "seconds": time.monotonic() - started}
