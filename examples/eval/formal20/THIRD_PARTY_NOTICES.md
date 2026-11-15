# 来源与第三方材料

本目录是本地 `harness-formal-20-v0.2` 在 2026-11-15 的任务材料导出。逐题来源见 `cases.json`，源元数据文件的 SHA256 见 `suite.json`。这里没有把所有任务宣称为上游原题，也没有为第三方材料重新授权。

| 材料 | 来源及保留的许可 |
| --- | --- |
| U01 的 Click 源码 | [Pallets Click](https://github.com/pallets/click)，8.1.7 冻结源码；保留 `cases/U01/input/LICENSE-Click.rst`（BSD 3-Clause）。 |
| U02 的文本分块源码 | [LangChain](https://github.com/langchain-ai/langchain)，text-splitters 1.1.2，与 [issue #40299](https://github.com/langchain-ai/langchain/issues/40299) 相关；MIT 许可补存于 `licenses/LangChain-LICENSE.txt`，取自上游 LICENSE，Git blob `3957738673765912ca83a0048f833e095d61e087`。 |
| U03 的 DeepTutor Python 源码 | 本地 DeepTutor v1.6.15（a31d826）的隔离快照，**人为移除一处已修复的同步恢复调用构造退化**，不是上游原始坏版本。Apache 2.0 许可证在 `cases/U03/input/LICENSE`；本地源码的第三方声明保存在 `licenses/DeepTutor-THIRD_PARTY_NOTICES.md`。 |
| C05 的 RPN 运算材料 | [QuixBugs](https://github.com/jkoppel/QuixBugs) 的任务适配；保留 `cases/C05/input/LICENSE-QuixBugs.txt`（MIT）。 |
| C01、U05 | 用户本地 `agent-minimal-loop` 的冻结代码及任务适配，不主张属于同名上游项目。 |
| U04、O02 | 本项目的路由、输入模型、数据库或文档节选及冻结导入证据。O02 描述的是冻结版本，不代表仓库最新版本的能力。 |
| C02–C04、O01、O03–O10 等 | 本地构造或适配的文件/工具/状态任务；O04 的设计参考 BFCL 风格，多轮内容与完成要求以本包题面为准，不主张官方 BFCL 测试成绩。 |

相对本地任务源，本次仅改动 U02/U03/U04/U05 四个 `.cmd` 启动器：移除作者机器上的解释器路径，改用 `EVAL_PYTHON` 或 PATH 中的 Python，保留原 unittest 参数。原始与导出的文件哈希均有记录。题面、其余初始输入、独立测试和参考修复未因发布被改写。

`environments/` 是依赖参考，不是各依赖源码的再分发，也不是完整历史环境锁定文件。依赖自身继续适用各自许可。
