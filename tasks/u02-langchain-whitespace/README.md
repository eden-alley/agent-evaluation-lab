# U02 可执行环境

这份任务包复用 LangChain #40299 的缺陷源码与既有 U02 判据。源码版本为 langchain-text-splitters 1.1.2，目标环境为 Windows x64、Python 3.12。本轮验证使用 Python 3.12.14。

先以 Python 3.12 运行初始化命令。以下命令均在本目录执行。

```powershell
python environment.py prepare
python environment.py validate
```

初始化会新建 work/runtime 虚拟环境，从 PyPI 安装 requirements.lock 中固定版本、带 SHA-256 的依赖。已有匹配安装包时可离线准备。

```powershell
python environment.py prepare --wheelhouse work/wheelhouse
```

初始化成功后，给被测 Agent 的工作目录为 work/workspace。instruction.md 保留原题面，workspace 中的源码和已有测试保留原始字节，run-tests.cmd 与 run-tests.py 使用任务包内的新解释器。参考修复和独立验收位于 evaluator，运行证据位于 work/evidence，接入 Harness 时由执行器限制 Agent 的访问范围。

在 workspace 中运行原题面约定的自测入口。

```powershell
.\run-tests.cmd
```

提交后在任务包目录运行自动验收。它使用独立的五项行为检查，核对允许修改的文件及 report.md 是否存在。报告内容与定位依据仍需复核。

```powershell
python environment.py grade
```

每次换模型、重试或比较版本前，用重置入口还原工作目录。它会先核对冻结材料，再清理上轮工作区并逐文件验证恢复结果。

```powershell
python environment.py reset
```

validate 从同一初态分别运行原缺陷、参考修复和过度清理三个对照，随后验证重置。预期原缺陷的公开检查失败，参考修复的独立五项检查全过，过度清理能通过公开检查但会被“关闭清理时保留空格”拦住。详细输出和 validation.json 保存在 work/evidence。

2026-11-12 的实测结果保存在 validation-result.json，关联任务清单、脚本和依赖锁的哈希。原缺陷通过 3/5、参考修复通过 5/5、过度清理通过 4/5，重置恢复了全部 18 个初始文件。Windows 自测启动器能返回失败退出码，修改已有测试会被自动范围检查拒绝。

环境包含初始源码、依赖和验收入口，工作目录和 Python 依赖各自隔离。操作系统级文件权限、网络封锁和被测 Harness 的启动由后续执行器落实。本轮验证覆盖 Windows，模型请求为 0。

源码与参考文件按 MIT 许可证分发，许可证见 LICENSE。原始问题见 https://github.com/langchain-ai/langchain/issues/40299 。本任务包新增了依赖锁、相对路径启动和环境验证脚本，参考修复用于检查验收的区分能力。
