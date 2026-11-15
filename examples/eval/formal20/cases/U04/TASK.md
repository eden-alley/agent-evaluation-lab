# U04 · 为真实项目列表接口增加向后兼容的分页

## 第 1 轮

项目管理页有 45 个项目。现在 GET /api/v1/projects 总是返回整份清单，页面希望按 20 条加载。请给现有 FastAPI + SQLite 路由加分页。

可选 limit 是 1–100 的整数，offset 是非负整数，提供 limit 时 offset 默认 0；只传 offset 或给非法值返回 HTTP 422。超过最后一页返回空 items。保持按 created_at、id 排序，同一份静态数据的相邻页面不重不漏，旧调用不传任何分页参数时保留原结果和 {items:[...]} 结构，其他项目接口不变。用 run-check.cmd 验证，交付源码和 report.md，保留已有测试；可新增回归测试，清理临时文件。
