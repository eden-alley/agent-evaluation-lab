# 输出容量与截断恢复

Harness v0.42 的 CLI 默认单次最大输出为 16,384 token，可用 `MODEL_MAX_OUTPUT_TOKENS` 调整。
这只是初始配置，尚未用真实模型验证最佳值。SDK 构造 Agent 时需显式设置 `output_truncation_recovery=1`；不传仍关闭恢复。

收到明确的 `finish_reason=length` 时，本条响应中的工具调用全部不执行，保留原响应和用量，提示模型用完整的小步骤继续。
一次 Agent.run（单轮执行）最多触发一次恢复；恢复后可继续多次读写，直到完成。再次截断、用量未知或预算不足会停止。
现有工具、权限、总预算和评分规则继续生效；不拼接残缺 JSON。

日常评测仍使用 `scripts/evaluation.py`。新配置在顶层明确设置：

```json
{
  "harness_version": "v0.42",
  "runtime_entry": "新冻结包/work/run-formal-current.py",
  "runtime_entry_sha256": "取自新冻结包/binding.json",
  "source_harness": "新冻结包/source",
  "output_policy": {
    "max_tokens": 16384,
    "timeout": 180,
    "output_truncation_recovery": 1
  }
}
```

本次本机冻结包位于 `C:\Users\叶宸玮\Documents\Codex\2026-11-16\d-projects-agent-harness-handoffs-2026\outputs\harness-v0.42-output-recovery`。
把其 `binding.json` 字段合入新任务配置，并将 `delivery.version` 设为 `v0.42`，再沿用日常入口的交付配置、冻结和逐次授权流程。
冻结时默认外层等待超时为 210 秒；若已显式设置 `timeout_after_ready` 或 `case_timeout`，须大于请求超时 180 秒。
外层等待超时用于检测请求停滞，不替代任务总预算。没有 `output_policy` 的旧计划仍保持原 4096/90 参数。

单题和对比详情页的“输出与恢复”区域只读取哈希校验通过的归档，分别显示截断、准备继续、完整响应、停止原因及原始记录链接。
完整响应不等于验收通过；历史记录缺失时不推断恢复成功，也不改旧分数。

本次验证为离线自动测试和脚本模型集成测试，真实模型调用为零。
