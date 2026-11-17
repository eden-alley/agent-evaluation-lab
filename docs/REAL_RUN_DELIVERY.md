# 真实运行后的归档与报告交付

`formal20_archive.py` 和 `formal20_pipeline.py` 只处理已经保存的执行产物，不调用模型、不执行任务、不重新评分。执行完成与报告交付完成是两个独立事实。

## 日常入口

统一使用 `scripts/evaluation.py` 的 `sync-skill`、`start`、`continue`、`submit` 和 `freeze`。启动前会核对固定统计能力、项目、A基线、固定方法版本与交付字段，拒绝执行字段在delivery里被改写。假API验证拒绝写日常data或日常8100。当前源码/模型有明确本机冻结默认值，实际值全部写入执行计划；不会搜索“最新”历史目录。

`start --config <json> --out <新目录>` 仅支持明确 `scripted_api/validation=true`。真实执行先 `freeze --config <json> --out <plan>`，取得当轮明确批准后，使用 `start --plan <plan> --approved-plan-sha256 <批准哈希> --out <新目录>`。真实供应商行为本轮没有调用验证。

用途、讲解题范围和归档版本均在执行前校验。所有公开执行入口共用启动保护：真实批准只能启动一次，同一平台的运行编号也会在开始时占用，防止未归档的批次撞号。Windows大小写同名不能分别启动，末尾句点别名与系统保留目录名在启动前拒绝。失败后保留原目录使用continue，不能换输出目录重新消费批准。假API的执行、归档与控制目录均不得进入日常data及其子目录。

start在完整执行后自动收尾，并返回 `task-handoff.json`、`继续本次任务.md`、固定Skill、材料、指标和可直接调用的 `submit_argv`。发起者继续同一任务读取材料、解释关键题、填写analysis，再 `submit --run <原目录> --analysis <文件>`，取得报告及回执后才完成A/B报告。程序不启动外部模型，也不会把空分析模板当成讲解。

`continue --run <原目录>` 使用原配置：执行已结束时只继续归档/准备/提交，不再调用模型或评分；未结束时按原生检查点检查，无法确认则返回needs_recovery。首批基线必须显式baseline-only；可以完成基线保存，但report_complete始终false，不声称有升降或报告。

同一运行只允许一个执行或恢复进程持有账本。从检查恢复现场到执行结束持有操作系统文件锁；第二个进程立即拒绝，不等待后再次执行。进程异常退出时锁由系统释放，留存的锁文件本身不阻止恢复，也无需手工删除。占用批准与运行编号的记录仍永久保留，不能借清理输出重新开预算。

方法源码更新后用 `sync-skill --api-url <明确地址>` 追加/复用发布本包的正文版本，再将返回的workflow三字段固定到新配置。新start核对当前包；已启动任务的continue及历史报告保留原版本，不跟随活跃方法漂移。轻量Skill规定同一发起者接续，不证明所有未来外部Agent都会遵从；程序只在有效回执后确认报告交付。

## 调用约定

```python
from formal20_pipeline import finalize_run, resume_delivery, submit_analysis_task

result = finalize_run(config, run_dir, api_client)
# 读取返回的 control_dir/Skill正文.md、materials.json、cases/<id>.json，
# 根据原件完成 analysis.json，再提交；程序不会编造分析。
result = submit_analysis_task(result['control_dir'], analysis_path, api_client)
```

`api_client` 由调用方显式注入，接口为 `request(method, path, **kwargs) -> dict`，HTTP错误和超时必须抛出异常。`path` 从 `/comparisons` 开始；HTTP client 自己绑定 `/api/v1`。可使用 `capability_review.Client(explicit_base_url)`，或包装实际 FastAPI `TestClient`；不要返回未检查状态码的错误 JSON。

配置至少包含：

| 字段 | 含义 |
| --- | --- |
| `run_id`, `project_id`, `project_name`, `name`, `model` | 本次运行及平台项目身份 |
| `version`, `source_harness` | 冻结 Harness 版本及来源指纹元信息 |
| `suite`, `case_ids` | 冻结题目元信息及本批题号；suite支持题目列表、含cases列表的对象、cases.json路径或其父目录 |
| `validation` | 假模型程序集成验证必须为true；导出会加offline validation用途和显示标签 |
| `archive_root` | 显式归档暂存根目录，生成 `<archive_root>/<run_id>` |
| `data_root` | 显式平台数据库父目录，发布到 `<data_root>/evaluation-runs/<run_id>` |
| `baseline_run_id` | 已在同一隔离平台发布的A运行；缺少时只保存归档，返回baseline_required |
| `workflow` | 固定 `{skill_id, version_id, content_hash}`，不选择当前活跃Skill |

可选 `control_dir`、`review_scope`（默认focused；正式整批显式formal_batch）、`explain_case_ids`、`analyst`、`analysis_origin`、`frontend_url`、`objective`、`comparison_name`、`dataset`。验证默认使用offline_fixture分析者和offline_program提交来源。3题及以内的建议限制由现有平台合同执行。

验证必须显式提供隔离app/client或绑定测试地址的client及data_root；缺少client、data_root或archive_root即拒绝，不会回落日常8100。平台health返回实际storage路径，真实HTTP与TestClient均核对data_root及evaluation-runs目的地；旧服务缺少storage时须先更新服务。执行目录、控制目录与归档目录存在包含关系时，在启动前拒绝，避免执行完成才发现无法交付。不能把日常数据目录作为验证目的地。

已有历史A/B的旧导入器可能保存更具体的task/checks/source/controls。可显式传 `task_metadata={case_id: original_task}` 以保留它们；导出会核对原题turns与allowed_changes相同，不能借元信息改题。新A/B应使用同一冻结suite和相同任务控制。指标是否可比仍由平台task identity与原判据校验；不以导入成功代替可比。

## 产物与状态

`export_run(config, run_dir, destination)` 读取 `<run>/<case>/result.json`、`grade/grade.json`、events、messages、workspace、检查点及其他题级原件，复制原字节；将grade原checks转换为现有平台checks列表，不调用评分器。缺失结果、unknown、invalid与未知费用不会变成零分或零费用。请求数读取本批budget及题级result，不使用历史某批常量。

新账本的题级tokens与已结算费用取最后一份完整权威records，按物理request_id只归并一次，不把每次账本快照重复相加。未知请求的已知用量另放known_字段，不能把已知部分展示成完整总量。旧产物没有可靠题级usage时继续保留未知，不按总量均分。

`publish_archive(stage, targetRoot)` 校验清单中的所有文件哈希，在同一文件系统、平台运行列表扫描范围之外建立临时副本，再原子发布；相同内容幂等，目标漂移或不同内容拒绝覆盖。manifest包含run.json，发布后不追加分析文件。

Windows下应给archive_root与data_root选择较短的绝对路径，为原工作区深层文件及发布临时目录名留出路径长度；路径过长导致复制失败时，不删改原证据来绕过。

控制文件默认位于运行目录同级 `<runname>-delivery`，必须在执行目录及不可变归档外：

```text
delivery-context.json       原配置和运行目录，恢复绑定
delivery-state.json         最后成功阶段及错误
import-receipt.json         归档路径、run_hash、manifest_hash
comparison-request.json    先保存的确定性创建请求
comparison.json            平台创建回执，含固定统计快照
metric-report.json / metrics-snapshot.json
preparation-request.json / preparation-attempt.json
packet.json                固定workflow、delivery_id、packet_hash
materials.json / 方法提供记录.json / Skill正文.md
cases/<case_id>.json / analysis-format.json
材料摘要.md / 指标升降表.md / analysis.json
request.json               先保存的真实ReviewSubmission
report.json / receipt.json  服务端报告和可核对回执
```

正常推进为 `execution_complete → archive_imported → statistics_ready → analysis_pending → report_received → delivery_complete`。`analysis_pending`表示材料已提供、分析未提交，不表示外部Agent已经阅读或开始分析。`delivery_complete`要求保存的报告和回执对应原request/packet；结构与引用检查通过不证明语义质量或建议有效性。

## 恢复

`resume_delivery(control_dir, api_client)` 读取原配置，重入未完成的收尾阶段，不启动任务、不重新评分。已保存的comparison/packet复用原件。创建响应丢失时，使用原comparison-request.json向服务端取回相同comparison。提交响应丢失时，使用原request.json、analysis.json、packet.json再提交，取得相同报告。

CLI 自动收尾只在执行完整结束后启动；checkpoint_paused 不发布最终不可变归档。成功 resume 后走同一收尾分支。需要保留未完成现场供诊断时应使用独立运行标识，不能用它覆盖最终运行。

同一任务不允许修改冻结配置、用途或指定讲解题。首次提交固定analysis和request；超时、网络断开、非JSON或服务端错误导致结果未知时，只能用相同输入取回同一回执，禁止改号重发。

服务器明确拒收时，程序保存拒收记录和原始分析。修正稿另存为新文件，再运行 `evaluation.py submit --run <原运行目录> --analysis <修正文件>`。程序在本任务下保留后续提交目录与原失败记录，成功后把有效回执接回原任务；`continue`读取该次提交，不重新执行Agent或评分。无需用户另开任务或手改冻结文件。材料确已过期时才按原用途和固定Skill重新准备；准备响应未知仍须停止核对。

后续提交的材料、分析、报告与回执以handoff返回的路径为准，根控制目录仍保存原任务配置和状态，不用它覆盖第一次失败请求。启动占用目录execution-approvals也是保留区域，执行和控制目录不能与它重叠。

现有prepare接口没有请求幂等键。若服务端已提供材料但响应丢失，程序保存preparation-attempt并停止，禁止自动再次prepare制造新delivery。需要找回该次原packet，放回同一控制目录后恢复；如果无法找回，应明确人工处理，不能声称已完成。缺baseline也不生成虚假升降，后续基线选择需显式建立新的对比流程。

## 离线验证边界

`scripts/tests/test_formal20_pipeline.py` 使用真实导出、manifest、发布、隔离FastAPI/SQLite及现有ReviewSubmission接口，验证无报告指标、幂等、阶段中断、创建/提交响应丢失、prepare不自动重做、原评分保留和未知项。它使用已保存材料fixture，不证明Agent运行、供应商配额、模型效果或实际并发速度。

运行记录保存在 `work/real-delivery/pipeline-tests.log`。Windows受限环境若阻止asyncio内部socketpair初始化，需要获准运行该离线TestClient测试；不能因此换成假的平台服务。
