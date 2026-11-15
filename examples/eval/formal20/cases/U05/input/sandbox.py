"""按用户要求新增：复用本机 Codex CLI 的 Windows 原生命令沙箱。

只调用 sandbox 子命令，不调用模型；启动失败时不回退为宿主机直接执行。
"""
import os
from pathlib import Path
import subprocess
import tempfile


# 不将 Agent 的 API key、代理认证、其他业务变量传给工具进程。
_ENV_NAMES = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "HOMEDRIVE", "HOMEPATH", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "CODEX_HOME",
    "USERNAME", "USERDOMAIN", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
    "PYTHONIOENCODING", "PYTHONUTF8",
}


def _codex_executable(workspace):
    # 只接受 PATH 中工作区以外的原生 exe，避免 .cmd/.ps1 外层 shell 提前执行命令。
    # 不搜索当前目录，也不使用相对 PATH 项，防止工作区中的同名程序顶替执行器。
    for entry in os.get_exec_path():
        directory = Path(entry.strip('"'))
        if not directory.is_absolute():
            continue
        candidate = (directory / "codex.exe").resolve()
        if not candidate.is_relative_to(workspace) and candidate.is_file():
            return candidate
    raise RuntimeError("找不到工作区外的 codex.exe；请安装或修复本机 Codex CLI。未执行命令。")


def _terminate_tree(process):
    taskkill = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
    try:
        subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def run_in_sandbox(command, workspace, timeout):
    workspace = Path(workspace).resolve(strict=True)
    executable = _codex_executable(workspace)
    cmd = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() in _ENV_NAMES}
    # 用批处理文件跨过两层 Windows 参数解析，保留 Python -c 等命令里的引号。
    # 这里只传脚本路径；脚本仍由沙箱内的 cmd 执行，宿主机不运行命令内容。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\r\n",
                                     dir=workspace, prefix=".agent-command-",
                                     suffix=".cmd", delete=False) as script:
        script.write("@echo off\nchcp 65001 >nul\n" + command + "\n")
        script_path = Path(script.name)
    argv = [str(executable), "sandbox", "-c", "windows.sandbox=mxc",
            "--include-managed-config", "--permission-profile", ":workspace",
            "-C", str(workspace), "--", str(cmd), "/d", "/s", "/c", ".\\" + script_path.name]
    try:
        with subprocess.Popen(argv, shell=False, cwd=workspace, env=environment,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                _terminate_tree(process)
                raise
            return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    finally:
        script_path.unlink(missing_ok=True)
