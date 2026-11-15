# O02 · 区分外部实跑导入与平台内启动评测

## 第 1 轮

同事看过产品设计说明，说评测页上的都是示例；另一个同事看见过一条真实运行，于是认为可以在平台上直接启动新评测。只根据 materials/ 中冻结的文档和证据，写 capabilities.json，告诉他们这个本地版本的行为。

输出 capabilities 对象，键 real_run_import（按本地合同导入外部真实运行）、real_run_display（平台展示这些运行）、platform_execution（在平台启动执行评测）、arbitrary_http_upload（通过公开 HTTP 接口随意上传真实运行），每项用布尔值。另输出 explanation（字符串），说明两份文档为何给出不同印象、哪个证据可确认当前版本、边界如何区分。列出 refs（引用数组，每项有 file、line、claim；使用 materials/ 相对路径和 1 起始行号，claim 取 historical、import、display、execution、http_upload）。引用应定位到支持相应结论的原文或源码。展示真实运行须引用导入观测，平台执行能力须引用后端能力证据。只写这个结果文件，保留现有资料，不访问正在运行的平台。
