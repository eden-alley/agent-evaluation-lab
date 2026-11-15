# C01 人工语义复核

核对冻结源码、resume-analysis.json 和已通过的引用位置，不按措辞或与参考答案的相似度评分。

1. `cli.py` 的 `interact` 识别 `/resume`，调 `handle_resume`，再调 `agent.resume`。
2. `Agent.resume` 在检查点存储租约下调用 `CheckpointStore.load`。后者读取 UTF-8 JSON、校验快照，缺文件时返回 None，坏格式错误与绑定不符分支可区分。恢复前通过 `inspect_checkpoint`。
3. `inspect_checkpoint` 比较已保存 binding 与当前 `checkpoint.binding`。模型绑定至少说明 provider、model_name 或 endpoint_hash 之一如何改变比较结果，工具至少说明 schemas 摘要或接入 MCP 时的 binding。另有与绑定不符无关的拒绝条件，例如 executing 的工具状态不明，禁止重放，或需要自定义 verifier 的跨进程任务。
4. ready 分支恢复 run state、消息，并调用 `_run_loop(..., resumed=True)`。若提到 finished，应说明它返回现成结果供 CLI 同步，不重复执行。
5. evidence_mode 或 verification 自称运行，只有轨迹确实显示相关验证时可按实跑认定。静态核对足够。

任一核心因果错误为 0，四段均解释正确且引用支撑时为 1，缺少可核对材料时留 unknown。
