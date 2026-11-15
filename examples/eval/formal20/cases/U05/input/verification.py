"""按任务配置的验收；默认循环不会调用任何验收模型。"""
from dataclasses import asdict, dataclass, field
import json
from typing import Callable

VERIFICATION_SYSTEM = """你是按明确条件工作的验收器，不执行工具，不增加任务要求。
输入提供任务、验收条件、候选回答、本轮工具证据和可用工具。
只能根据证据检查给定条件，不能把助手声称完成当作证据。
pass：给定条件已满足；fail：未满足且主模型仍有可执行的修正步骤。
needs_input：确实缺少用户提供的信息或真实授权；工具不可用不等于用户拒绝。
error：当前证据或验收方式不足以判断。需要用户补充信息时不得返回 fail 推动空转。
仅输出 JSON：{"status":"pass|fail|needs_input|error","reason":"具体依据","evidence":[]}。
"""


@dataclass(frozen=True)
class CheckResult:
    status: str
    reason: str
    evidence: list = field(default_factory=list)

    def __post_init__(self):
        if self.status not in ("pass", "fail", "needs_input", "error"):
            raise ValueError("验收状态必须为 pass、fail、needs_input 或 error")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("验收 reason 必须是非空字符串")
        if not isinstance(self.evidence, list):
            raise ValueError("验收 evidence 必须是列表")
        json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class VerificationInput:
    task: str
    candidate: str
    tool_results: list
    available_tools: list
    run_tool: Callable = field(repr=False, compare=False)


class ModelVerifier:
    """显式选用时才调用模型；输入只包含本任务证据，不包含整段历史。"""
    def __init__(self, model, criteria, record_usage):
        if not isinstance(criteria, str) or not criteria.strip():
            raise ValueError("需要明确的验收条件")
        self.model = model
        self.criteria = criteria
        self.record_usage = record_usage

    def __call__(self, context):
        payload = {"task": context.task, "criteria": self.criteria,
                   "candidate": context.candidate, "tool_results": context.tool_results,
                   "available_tools": context.available_tools}
        response = self.model.query([
            {"role": "system", "content": VERIFICATION_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        self.record_usage(response.usage, "验收")
        message = response.require_message()
        if message.get('tool_calls'):
            raise ValueError("模型验收器不允许调用工具")
        result = json.loads(message.get('content') or "")
        if not isinstance(result, dict):
            raise ValueError("验收输出必须是 JSON 对象")
        return CheckResult(**result)


def command_verifier(command):
    """复用已有检查命令；执行仍经过 Agent 的工具、权限和沙箱。"""
    def verify(context):
        result = context.run_tool("run_shell", {"command": command})
        evidence = [result.to_dict()]
        if result.ok:
            return CheckResult("pass", "检查命令成功退出", evidence)
        if result.exit_code is not None:
            return CheckResult("fail", "检查命令未通过，请根据输出修正", evidence)
        if result.code in ("user_denied", "confirmation_unavailable"):
            return CheckResult("needs_input", result.message, evidence)
        return CheckResult("error", result.message, evidence)
    return verify
