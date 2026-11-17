# 可配置并发执行器

`formal20_concurrent.py` 提供可配置的题目进程调度。每题独立工作区，通过 Pipe 向一个协调进程申请请求许可；协调者统一记录预算、全局请求间隔、在途上限和异常停止。单题内部按顺序执行。

`simulate` 保留合成回归。`execute` 使用冻结原题、原 Agent、原生工具和原评分器；`scripted_api` 只替换 SDK 响应，用于隔离集成验证，绝不回退真实模型。真实 `provider_api` 需新的完整冻结计划与该轮明确授权；本轮未调用。

真实路径用法（config 显式指定 case_ids、transport、validation、固定响应及输出/预算等参数）：

```powershell
python -B scripts/formal20_concurrent.py freeze --config work/validation-config.json --out work/frozen-plan.json
python -B scripts/formal20_concurrent.py execute --plan work/frozen-plan.json --transport scripted_api --validation --out work/new-run
python -B scripts/formal20_concurrent.py inspect --run work/new-run
python -B scripts/formal20_concurrent.py resume --plan work/frozen-plan.json --run work/new-run
```

计划绑定题面/输入/judge-only、冻结源码、评分脚本、本地执行器、依赖与有效模型参数。目录必须不存在；恢复复用原目录和账本。不能通过改计划、切换模型或清空费用继续。原入口目前来自本机冻结快照，迁移机器需显式配置并校验材料，不提供自动下载或自动选择“最新版本”。

运行完成后可通过配置中显式的 `delivery.api_url`、隔离data_root、基线和Skill版本调用收尾。程序先归档、保存指标和提供材料；外部Agent仍需读取Skill并提交分析。页面的待分析状态与有效报告回执分开。见 [交付合同](../docs/REAL_RUN_DELIVERY.md)。

在项目根目录，用 Python 3.11+ 执行，输出目录必须不存在：

```powershell
python -B scripts/formal20_concurrent.py simulate --workers 1 --out work/sim-1
python -B scripts/formal20_concurrent.py simulate --workers 2 --out work/sim-2
python -B scripts/formal20_concurrent.py simulate --workers 4 --out work/sim-4
python -B scripts/formal20_concurrent.py simulate --workers 8 --out work/sim-8
python -B scripts/formal20_concurrent.py simulate --workers 8 --max-inflight-requests 2 --out work/sim-8-cap2
```

`workers` 接受正整数，默认 2；在途请求上限独立设置，默认跟随 workers。`--request-interval-ms 100` 表示全部题共享至少 100ms 的许可间隔。增加进程数不会扩大预算或跳过限流。这些值是离线配置，不代表模型服务实际配额。

默认场景是 20 道 `SIM-*` 合成任务，每题两个固定响应。故障场景可用 `--scenario api_error`、`crash`、`timeout`、`unknown_usage`、`unexpected_checkpoint`；`checkpoint` 验证预期中断恢复，`checkpoint-stop` 验证停批后不恢复。每个场景用独立目录。正常完成退出 0；有停止、故障或未运行题退出 2，不能把程序正常收尾当成全部完成。

目录包含：

- `config.json`：实际采用的并发、限流及模拟预算配置。
- `budget.json`：已结算估算金额、未结算预留、许可/响应/未知计数。
- `requests.jsonl`：协调者唯一写入的请求、响应与异常记录。
- `batch-events.jsonl`：进程启动、任务开始及结束，用于回查实际重叠。
- `SIM-*/`：各题独立工作区、事件、结果及合成检查点。
- `summary.json`：原题序的完整状态、批次挂钟时间、题级时间之和、排队等待和许可至响应回报的等待之和。后者包含进程通信开销，不是纯模型服务延迟。

API 异常默认停止新增许可与新题，排空已许可请求。显式冻结 max_retries=1 才允许一次指定临时错误重试，新增物理请求且保留前次未知费用。未知用量不清零。`request-ledger.jsonl` 记录许可、响应和消费，先持久化响应再交Agent；安全恢复重放已保存响应，不重复调用SDK。原生检查点先核验绑定和副作用状态，无法确认时返回 needs_recovery。父进程使用 worker-state.json，不覆盖原result/grade。

合成回归保护仍拒绝原题读取。假API真实路径允许冻结依赖及指定loopback服务，禁止外网/真实客户端，并清理凭据环境。命令始终经过原生沙箱，不用宿主shell兜底。

运行离线程序测试：

```powershell
python -B -m unittest discover -s scripts/tests -p 'test_formal20_*.py' -v
```

测试覆盖合成回归、真实路径与归档/平台合同；集成证据记录实际PID、请求重叠、原生工具和原评分源码指纹。固定响应耗时不代表真实模型加速比例，原评分结果也不代表模型能力改善。
