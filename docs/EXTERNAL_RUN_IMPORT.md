# 外部真实运行展示

2026-11-12 增加 U05 保存交付物的独立检查：任务可关联固定检查程序，使用归档副本产生新的检查记录和证据，不覆盖原运行或历史复核。此入口只运行登记的 Windows 沙箱检查程序，不启动 Agent 或模型。接口、版本和证据边界见 [保存交付物的独立检查](SAVED_DELIVERY_CHECKS.md)。原有 archive/mock 评审与独立检查分开显示。

2026-11-12 新增独立评审流程。真实归档仍由本文的只读接口读取；评审任务、Skill 快照与人工追加终判保存在 SQLite 的独立表。POST /evaluation-runs/{run_id}/judgments 发起 archive 或 mock 任务，GET 同路径列出记录，GET /{job_id} 读取结果，POST /{job_id}/reviews 追加人工决定。当前模式均无模型调用。

archive 明确引用历史判定而未独立重验，mock 明确标记模拟；默认当前能力展示最新 archive，模拟记录单独选择。原归档验收和本次评审状态各有标签。unknown/缺证据与 pending/待人工复核分别展示。

本地工作区的 `/evaluations` 和 `/evaluations/{id}` 展示已在外部执行并导入的真实记录；`?mode=example` 继续使用原演示数据。没有新增模型执行入口，`evaluation_execution` 仍为 false。

数据集经现有 MCP / HTTP 合同保存不可变草案、质量报告与确认版本。运行记录单独存放在数据库同级的 `evaluation-runs/{id}/run.json`，绑定项目、数据集版本和内容哈希。它是本机导入目录，不是上传 API 或自动发现任意宿主文件的机制。

`manifest.json` 列出归档文件相对路径、字节数和 SHA-256。只读 HTTP 接口为 `GET /api/v1/evaluation-runs`、`GET /api/v1/evaluation-runs/{id}` 和 `GET /api/v1/evaluation-runs/{id}/artifact?path=...`。只提供清单内且仍位于导入目录中的文件，每次读取核对哈希。路径越界或未列出文件拒绝读取；大于 2 MiB / 二进制文件提供下载，下载作为 attachment 并设置 nosniff，不执行交付代码。

页面保留逐项 1 / 0 / unknown、核心与诊断判据、原自动值、复核值、任务全文、输入文件、轨迹和产物。没有生成跨维度总分，也没有把质量报告的覆盖数当成运行成绩。来源数据和运行内容的真实性仍由外部证据支持；平台的哈希核对只证明导入后内容未变化。

2026-11-09 已按用户确认导入 20 例基线：数据集 v1，真实 242 次请求，核心验收 18 通过、2 未通过，保守费用 US$0.3896097。导入前 SQLite backup；旧草案和示例保留。导入和验收脚本、回执放在本轮工作区 `outputs/platform-boundary20-import` 与 `work/import-boundary20-to-lab.py`、`work/verify-boundary-platform.py`。

验证：后端完整回归 31 passed / 1 skipped（Windows symlink 权限），前端现有测试 14 passed，TypeScript 与生产构建通过；新增后端测试覆盖真实列表、unknown 原值、原件下载、越界/未列出文件拒绝及哈希变更拒绝。
