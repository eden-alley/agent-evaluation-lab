# 现有评测执行器并发改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 2026-11-16 用户已授权实施；本阶段仅做离线合成验证，真实执行入口保持关闭。

**Goal:** 将现有外部执行器接入可配置的题目并发、每题独立进程与工作区、统一预算和限流，先用合成任务在 1、2、4、8 并发下验证调度、异常停止、记账和结果汇总。

**Architecture:** 保留历史执行入口，由新的并发入口复用已有单题执行逻辑。一个协调进程按 `workers` 配置管理题目进程，通过进程间 Pipe 收发请求许可与结果；只有协调者写批次账本和汇总。平台继续接收原有运行归档，本阶段只验证外部执行器，不增加平台调度。

**Tech Stack:** Windows、Python 3.11+、标准库 `subprocess` / `multiprocessing.Pipe` / `multiprocessing.connection.wait` / `Decimal` / `unittest`；不增加运行依赖。

**Spec:** 本轮用户要求及下文“范围与设计约定”。本文件同时记录设计取舍和实施步骤，无需另建工作流或审批系统。

## Global Constraints

- 本阶段实施及验证限于合成离线任务，不提交或推送 GitHub。
- 后续第一阶段只运行合成任务与固定响应，不调用真实模型、不读取 API 凭据、不重跑原 20 题、不执行原评分器。
- 原题、原评分、被测 Harness、原生沙箱、历史运行和批准记录保持原字节。
- `--workers` 接受正整数，默认值 2 只是起步配置，不是能力上限；离线验证必须覆盖 1、2、4、8。拒绝零、负数及非整数，不因任务数较少启动空闲进程；单题内部的对话、工具、验收顺序保持原样。
- 不自动重试模型请求，不把 worker 意外退出当作重新做题的理由。
- 不改轻量 Skill、平台页面、数据表、导入合同或全目录哈希判据；性能优化只限题目调度。
- 离线模拟不证明模型效果、真实服务限流、Windows 原生工具或原评分兼容性已经通过实跑。
- 真实运行需要新的冻结计划和本轮运行授权；旧批准不覆盖并发入口、并发参数及停止语义的变动。

## 范围与设计约定

### 1. 已核实的现状

最新入口位于评测工作目录的 `outputs/harness-v0.40-formal20-20261115/work/run-formal-current.py`，评测工作目录为 `C:/Users/叶宸玮/Documents/Codex/2026-11-06/new-chat-5`。

- 第 584–602 行逐题调用 `execute_case()`，并发数为 1。
- 第 86–88、109–161 行用一个 `inflight` 和共享 `budget.json` 管理请求，不能直接并行读改。
- 第 352–430 行已有逐题工作区、阶段快照、事件、结果和评分入口，可复用。
- 第 288–304、528–537 行已有 O08 中断/恢复控制；一次预期恢复仍属于同一道任务。
- 第 333–349 行会替换评分模块的全局读取器和工具入口，独立进程可避免各题互相影响。

该文件是已经归档的执行依据，**实施时也不回写它**。当前 SHA256 为 `d4a353b49ecb3da046b58e761eef0005edab5da1323e39367dcdaafd3b8b8e8e`。新入口在项目内维护，通过显式的 `source_entry` 路径只读加载这份已核对的执行器；加载前核对指纹。初次加载只发生在题目进程，不让父进程导入可变评分模块。

### 2. 实施位置与接口

以下为本阶段实现文件：

| 文件（相对项目根目录） | 职责 |
| --- | --- |
| `scripts/formal20_concurrent.py` | CLI、并发槽位、子进程生命周期、批次状态和汇总 |
| `scripts/formal20_coordinator.py` | 唯一预算所有者、全局限流、请求日志和持久化快照 |
| `scripts/formal20_worker.py` | 合成任务后端、旧单题执行器适配、单题 Pipe 通信与局部日志 |
| `scripts/tests/test_formal20_concurrent.py` | 合成进程集成测试及原接口适配测试 |
| `scripts/tests/test_formal20_accounting.py` | 预算、幂等结算、限流及错误条件测试 |
| `scripts/README-formal20-concurrent.md` | 离线命令、记录口径、停止语义和真实运行前的边界 |

协调器的核心接口：

- `acquire(case_id, attempt_id, reserve_cost, prompt_metadata)`：通过预算与限流后返回稳定的 `request_id` 和全批次请求序号；等待期间可取消。
- `settle(request_id, usage, response_metadata)`：结算一次；相同重复消息返回已有结果，冲突消息触发协议错误。
- `stop(reason)`：记录全局停止点，不再发放新请求许可或启动新题。
- `snapshot()`：输出请求计数、已结算估算金额、未结算预留、停止原因和各题状态。

由 `Coordinator` 类持有上述接口和状态；请求按 `case_id + attempt_id` 幂等，同一题没有并行请求。题目进程不直接读改总账或追加批次日志。`acquire` 先入队，由消息循环择时授予，不能阻塞协调器等待预算或限流，否则会妨碍它处理其他题的结算。

### 3. 预算、限流与停止的具体含义

**预算：** 使用 `Decimal`，沿用原有保守费用预留公式和币种，不重新估价。发许可前，必须满足：`已结算估算金额 + 所有未结算预留 + 新请求预留 <= 总预算`，并同时满足整批和单题请求上限。许可持久化后才回复 worker；同一笔请求不重复占次数或费用。

在测试的模拟金额单位下，两个进程同时各申请 6、总预算为 10 时，只准一个。若它以 2 结算，则另一笔 6 可以继续；因在途预留不足时先等待，不能提前判断整批预算耗尽。没有在途请求、仍无法承担下一笔时才按原预算停止原则停批。

已经发出许可但失联的请求，不能证明未发送，保留其预留并标记 `unknown_usage`。只有已知未获发送许可的排队请求可直接取消。展示“许可次数、已确认响应数、未知请求数”，不把许可次数冒充已确认模型调用数。估算及预留不是实际账单的保证。

**限流：** 题目并发数 `workers` 与请求上限 `max_inflight_requests` 分开配置。后者接受正整数，未指定时取 `workers`；同题请求顺序执行，因此实际在途数不超过 `min(workers, max_inflight_requests)`。全局请求最小间隔在离线场景中显式配置，例如 1,000 毫秒；这只是验证参数，不声称是模型服务的配额。用单调时钟、全局 FIFO 等待队列，所有 worker 共享限流，增加进程数不会增加全批次预算或绕过请求间隔。网络或模拟响应等待不占用协调器的记账处理时间。

离线矩阵固定为 `workers ∈ {1, 2, 4, 8}`，覆盖各档正常完成、预算竞争、限流、异常停止、恢复和汇总；另外验证 `workers=8, max_inflight_requests=2`，证明同时做多道题时仍能限制请求数量。单并发不等待多人屏障，也不要求存在另一条在途请求；这些并发专用断言仅适用于 2、4、8。

**停止：** 从协调器记录停止事件起，不再发新许可、新题或恢复任务。此前已授予许可的请求视为在途，允许在原请求超时内收尾并结算；失败或缺用量的请求保留预留，不重试。若 worker 卡死，超时后结束其进程树，记录未确认状态，不能清零费用或冒充正常完成。

API 错误、响应配置漂移、未知用量、账本写入失败、worker 非预期退出均停整批；原单题次数上限只终止本题，整批上限终止批次。普通任务未通过验收仍是有效任务结果，不因失败分数停批。

### 4. 工作区、日志与结果

- 每题独立 PID、模块状态、工作区、阶段快照、checkpoint、事件及评分目录，路径继续采用 `run/<case_id>/...`；拒绝重复题号及已存在的运行目录。
- 新运行目录必须位于原评测工作目录的 `outputs/` 下，让现有 MXC 路径隔离仍覆盖相邻任务、评测材料和协调器文件；不因换并发入口放宽沙箱。离线模拟只验证路径与进程隔离，不宣称已验证原生沙箱。
- 协调者唯一追加批次 `requests.jsonl`，每题保留原 `events.jsonl`；全局请求序号唯一，单题事件序号无需跨题统一。
- `budget.json` 保留旧单题逻辑使用的 `requests`、`per_case`、token 及金额字段；多请求状态新增 `inflight_requests`。不让旧 `main()` 误读新状态，新入口只复用单题函数。
- 单题记录完成即原子保存，不等待整批结束。批次汇总按输入题序输出，不按完成先后改题序。
- 执行状态与原 `verdict/checks` 分开：未运行、基础设施错误、用量未知均不能计为模型失败；保存原评分结果，不根据进程退出码替代评分。
- 同时记录批次挂钟时间、各题耗时之和、排队等待、请求等待；并发后这些数不同，不能再用题级耗时之和代表整批耗时。
- 离线输出显式 `mode=offline_simulation`，只用 `SIM-*` 题号，不生成可被误导入为真实评测的 `run.json`。

## Review Focus

1. 并发申请与结算顺序不同，不能超预算、漏记、重复结算或把未知用量当零：由任务 1 测试。
2. 一个 worker 出错时，其他所有已许可请求仍需结算，停止后不能再发许可：由任务 3 测试。
3. Windows 子进程导入、全局模块替换和相邻工作区不能互相污染：由任务 2 测试。
4. 预期检查点退出与普通崩溃不能混淆，恢复不能重置计数或重复写回执：由任务 3 测试。
5. 乱序完成、部分批次和退出码 0，不能被汇总成“全部完成”或误称真实评测：由任务 4 测试。

---

## Task 1：实现唯一预算所有者和全局限流

**Files:** Create `scripts/formal20_coordinator.py`; Test `scripts/tests/test_formal20_accounting.py`。

**Interfaces:** 提供 `acquire`、`settle`、`stop`、`snapshot`；时钟可注入；接口返回值通过 Pipe 使用可序列化字典。

- [x] 先写失败测试：`test_two_reservations_cannot_overspend`，两笔各 6、预算 10，只准一笔；第一笔结算为 2 后第二笔可发。
- [x] 补 `test_request_and_settlement_are_idempotent`、`test_conflicting_settlement_stops_batch`、`test_unknown_usage_keeps_reservation`；分别断言不重复计数、不接受冲突用量、未知预留不释放。
- [x] 用可控时钟写 `test_global_request_interval_and_inflight_cap`：对 1、2、4、8 并发分别验证许可时间满足全局 1,000ms 间隔，在途数不超过配置上限；补 `test_worker_count_and_request_cap_are_independent`，验证 8 个题目槽、请求上限 2 时最多 2 条在途；无需等待真实模型或长时间 sleep。
- [x] 补 `test_batch_and_case_request_limits`、`test_ledger_write_failure_grants_no_permission`，覆盖次数边界与预留落盘失败。
- [x] 运行 `python -B -m unittest discover -s scripts/tests -p test_formal20_accounting.py -v`，确认失败原因，再实现最小记账与限流；重复同命令应全部通过。

## Task 2：接入可配置并发、单题进程隔离和旧单题适配

**Files:** Create `scripts/formal20_concurrent.py`, `scripts/formal20_worker.py`; Test `scripts/tests/test_formal20_concurrent.py`。

**Interfaces:** `run_batch(config, cases)` 返回批次汇总；worker 接收单题配置与 Pipe。配置至少含 `workers`、`max_inflight_requests`、运行目录、题目后端、全局请求间隔及预算，实际采用的值必须保存到批次配置和汇总；后端通过显式标记选择合成任务或原执行器适配，默认只能离线模拟。

- [x] 写 `test_configured_process_limit_and_overlap`：对 `N ∈ {1, 2, 4, 8}` 提供 `N+1` 道合成题，证明活跃题不超过 N；N 大于 1 时前 N 题不同 PID 在屏障相遇，下一题等槽释放后开始；N 为 1 时验证完全串行，不能用多人屏障或只用耗时比判断。
- [x] 写 `test_workspaces_and_module_state_are_separate`：各并发档位的不同题写同名文件、改模块变量，结果各自独立；补配置校验用例，覆盖零、负数、非整数、题数少于槽位、重复题号和已有目录拒绝。
- [x] 实现 `spawn` 方式的 Windows 子进程、每题一个 Pipe、协调器消息循环。父进程不运行单题模型或评分逻辑。
- [x] 实现原单题调用形状与预算代理适配（仅合成模块探针验证；真实入口仍拒绝启动）：固定 `source_entry`，在该题进程内用 RPC 版 `RequestGuard` 替代共享 JSON 记账；原 `execute_case`、评分函数、MXC 与任务控制照原入口调用。
- [x] 写 `test_legacy_adapter_delegates_without_shared_writes`：用假的旧入口与函数探针验证参数、模块进程边界、工作区和预算代理，不能运行真实评分器。真实运行入口本阶段拒绝启动。
- [x] 执行 `python -B -m unittest discover -s scripts/tests -p test_formal20_concurrent.py -v`，先看到失败，再实现并确认本任务用例通过。

## Task 3：覆盖停批、异常排空和预期中断恢复

**Files:** Modify 任务 1、2 的三个实现文件及两个测试文件。

**Interfaces:** 协调者持有全局 `halt`；worker 返回执行结果或预期中断记录，不自行重做失败任务。

- [x] 写 `test_api_error_stops_dispatch_and_drains_inflight`：对 1、2、4、8 并发分别验证，一题报模拟 API 异常后不再发新题或新许可，其他所有已许可请求仍结算，重试次数为 0；为各档准备多于槽位的任务来验证队列停止，单并发不强求存在其他在途请求。
- [x] 写 `test_worker_death_keeps_unknown_reservation` 和 `test_timeout_finishes_with_partial_results`：进程突然退出或卡住时账本仍可读，未知费用保留，队列不死锁；测试使用短超时，不读真实凭据。
- [x] 写 `test_coordinator_disconnect_blocks_further_requests`：协调器退出或 Pipe 断开后，worker 停止申请和后续模型步骤，不能绕过许可继续执行；本阶段不自动恢复已崩溃的批次协调器。
- [x] 写 `test_recorded_checkpoint_resumes_once`：仅 `SIM-CHECKPOINT` 合成题按已保存、已记账且无在途请求的边界返回预期退出码 86，从同一工作区恢复；回执写入次数为 1，请求累计不重置，恢复期间逻辑槽位不释放。
- [x] 写 `test_unexpected_exit_86_does_not_resume`、`test_global_halt_blocks_checkpoint_resume`；没有可信中断边界或已经停批时不得恢复。
- [x] 将进程退出、超时、Pipe 断开、预期恢复与恢复被拒等场景覆盖到 1、2、4、8 并发，实现最小停止与恢复控制后重跑上述测试确认通过。这里只模拟 O08 所需协议，不执行真实 O08、不宣布其真实恢复已验证。

## Task 4：验证汇总和整条离线链路

**Files:** Modify `scripts/formal20_concurrent.py`, `scripts/tests/test_formal20_concurrent.py`; Create `scripts/README-formal20-concurrent.md`。

**Interfaces:** `simulate` 命令走与并发入口相同的协调、记账、写盘路径，worker 仅使用固定合成动作与响应；输出 `summary.json`、`budget.json`、`requests.jsonl` 和逐题结果。

- [x] 写 `test_summary_is_ordered_and_partial_is_explicit`：SIM 题乱序完成，汇总仍按原题序；已完成、故障、未知、未运行分别计数，退出码不能充当全部完成标记。
- [x] 写 `test_serial_and_parallel_simulations_agree`：同一无故障场景分别用 1、2、4、8 个 worker，与单并发基线比较，结果、次数和总用量相同，允许时间和完成顺序不同；预算与限流保持全局口径，不随 worker 数倍增。
- [x] 写 `test_offline_mode_never_loads_credentials_or_grader`：父子进程均禁止模型 SDK 客户端、凭据读取和评分模块加载，禁止外部网络；进程通信只用 Pipe，不用本地 HTTP。故意触发任一入口应立刻失败。
- [x] 设计 20 个 `SIM-*` 合成任务覆盖正常、限额、异常和检查点场景；固定响应不读取原题参考结果、不复制真实轨迹伪装模型输出。
- [x] 分别运行 `python -B scripts/formal20_concurrent.py simulate --workers <N> --out <该档新的离线目录>`，N 依次为 1、2、4、8，验证完整链路的 PID、活动区间、账本等式、零重试及汇总；再用 `--workers 8 --max-inflight-requests 2` 验证两类限制独立生效。每档每个异常场景使用独立目录，不能一个故障场景提前停批后声称覆盖全部情况。
- [x] 文档写清：离线测试证明了什么、哪些还未验证、如何读部分结果；CLI 不开放真实运行，也不自动导入平台。

## Task 5：收尾与交付证据

**Files:** 仅涉及本计划列出的新增文件；历史目录只读。

- [x] 运行 `python -B -m unittest discover -s scripts/tests -p 'test_formal20_*.py' -v`，确认所有并发、记账、异常及汇总用例通过；不启动原控制脚本或原 20 题。
- [x] 以实施前保存的指纹复核原入口、评分器、任务材料和 Harness 未改变；不要事后重建“修改前”指纹。
- [x] 交付一份简短离线回执，逐档列出 1、2、4、8 的配置与实际最大并发、请求在途上限、许可/响应/未知计数、结算/预留金额、限流时间点、停止后的处理和逐题汇总；不能只报告默认档位。
- [x] 明确未做真实模型并发、服务端限流测量、原生沙箱并发或原评分实跑；离线模拟耗时不当作正式评测加速比例。
- [x] 仅向用户展示本地改动与离线回执，不提交或推送 GitHub；后续运行与发布按用户的新指令进行。

## 最终验收

在 1、2、4、8 每个档位同时证明：实际活跃题不超过配置且互不污染，单并发顺序执行，多并发确实重叠；预算与限流全局统一且不随进程数倍增；错误发生后不再派发且所有在途请求完成记账；预期恢复不重复业务写入；汇总准确区分完成与未完成。另外证明 8 个题目槽也可独立限为最多 2 条在途请求。任何一项失败，都不能以“进程启动成功”宣布并发改造完成。

当前状态：**离线阶段完成：31 个程序测试、45 个矩阵场景通过；原 1,615 个受保护文件指纹不变。真实模型、原生沙箱并发和原评分兼容性未实跑。**
