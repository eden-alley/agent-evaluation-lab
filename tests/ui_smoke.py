"""Local framework browser acceptance; uses only the isolated test API database."""
import json
import os
from uuid import uuid4
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

PROJECT = Path(__file__).resolve().parents[1]
TASK = Path(os.environ["LAB_TEST_WORKDIR"]).resolve()

OUT = TASK / "work" / "ui-check"
OUT.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:3100"
PROJECT_NAME = "UI 验收项目-" + uuid4().hex[:6]
results = []

def record(name):
    results.append({"name": name, "status": "passed"})
    print("PASS", name, flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width":1440,"height":1000}, device_scale_factor=1)
    console_errors = []
    page.on("pageerror", lambda error: console_errors.append(str(error)))

    page.goto(BASE + "/evaluations", wait_until="networkidle")
    expect(page.get_by_role("heading", name="暂无评测运行")).to_be_visible()
    expect(page.get_by_text("候选运行",exact=True)).to_have_count(0)
    assert page.get_by_role("navigation").get_by_role("link").count() == 6
    record("Actual workspace is empty and separated from example results")

    page.get_by_role("link", name="查看示例", exact=True).click()
    page.wait_for_url("**/evaluations/example-candidate?mode=example")
    expect(page.get_by_text("示例预览模式",exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="候选运行",exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "evaluation-desktop.png"), full_page=True)
    record("Evaluation frame loads with persistent fixture provenance")

    page.get_by_role("button",name="工具报错后的恢复",exact=True).click()
    evidence = page.locator(".section-gap").filter(has=page.get_by_role("heading", name="证据详情 · 工具报错后的恢复"))
    expect(evidence).to_be_visible()
    evidence.get_by_role("button",name="证据来源：a000000000020003",exact=True).first.click()
    expect(evidence.locator(".detail .code")).to_contain_text("file_not_found")
    page.screenshot(path=str(OUT / "evidence-desktop.png"), full_page=False)
    record("Grade evidence navigates to matching tool result")

    page.get_by_role("button",name="返回案例列表",exact=True).click()
    page.get_by_label("筛选状态").select_option("error")
    expect(page.get_by_role("button",name="超时后保留执行记录",exact=True)).to_be_visible()
    assert page.locator(".table-wrap tbody tr").count() == 1
    page.get_by_role("button",name="超时后保留执行记录",exact=True).click()
    expect(page.get_by_text("执行错误：工具执行超时，未产生最终输出。",exact=True)).to_be_visible()
    record("Error filtering includes timeout with retained evidence")

    page.goto(BASE + "/datasets?mode=example",wait_until="networkidle")
    expect(page.get_by_text("显示 12 / 12",exact=True)).to_be_visible()
    page.get_by_label("案例分类").select_option("文件读取")
    expect(page.get_by_text("显示 3 / 12",exact=True)).to_be_visible()
    page.get_by_role("button",name="本地 JSONL 预览",exact=True).click()
    row=json.dumps({"schema_version":1,"case_id":"x","input":{"prompt":"test"},"expected":None},ensure_ascii=False)
    page.get_by_label("选择 JSONL 文件").set_input_files({"name":"valid.jsonl","mimeType":"application/x-ndjson","buffer":row.encode()})
    expect(page.get_by_text("校验通过 · 1 条案例 · 分类：无",exact=True)).to_be_visible()
    page.get_by_label("选择 JSONL 文件").set_input_files({"name":"duplicate.jsonl","mimeType":"application/x-ndjson","buffer":(row+"\n"+row).encode()})
    expect(page.get_by_text("第 2 行：case_id 重复。",exact=True)).to_be_visible()
    record("JSONL preview validates locally and rejects duplicate IDs")

    page.goto(BASE + "/comparison?mode=example",wait_until="networkidle")
    metrics=page.locator(".metric")
    expect(metrics.filter(has_text="退化案例").locator("strong")).to_have_text("2")
    expect(metrics.filter(has_text="修复案例").locator("strong")).to_have_text("1")
    page.screenshot(path=str(OUT / "comparison-desktop.png"),full_page=True)
    page.get_by_label("候选运行",exact=True).select_option("example-baseline")
    expect(page.get_by_text("请选择两个不同的运行进行比较。",exact=True)).to_be_visible()
    record("Comparison derives two regressions and one fix; same-run comparison rejected")

    page.goto(BASE + "/projects",wait_until="networkidle")
    page.get_by_role("button",name="新建项目",exact=True).click()
    page.get_by_label("项目名称",exact=True).fill(PROJECT_NAME)
    page.get_by_label("需求与评测目标",exact=True).fill("仅存在于独立测试数据库")
    page.get_by_role("button",name="保存项目",exact=True).click()
    expect(page.get_by_text("项目已保存。",exact=True)).to_be_visible()
    page.reload(wait_until="networkidle")
    page.get_by_role("button",name=PROJECT_NAME,exact=True).click()
    expect(page.get_by_label("智能体名称",exact=True)).to_be_enabled()
    fixture_dir=OUT / "agent-fixture"
    fixture_dir.mkdir(exist_ok=True)
    (fixture_dir / "agent.py").write_text("raise RuntimeError('must not execute during static check')",encoding="utf-8")
    page.get_by_label("智能体名称",exact=True).fill("Static check fixture")
    page.get_by_label("源码目录",exact=True).fill(str(fixture_dir))
    page.get_by_label("Python 解释器路径",exact=True).fill(str(PROJECT / ".venv" / "Scripts" / "python.exe"))
    page.get_by_label("入口文件（相对源码目录）",exact=True).fill("agent.py")
    page.get_by_role("button",name="保存智能体",exact=True).click()
    expect(page.get_by_text("智能体配置已保存。",exact=True)).to_be_visible()
    page.get_by_role("button",name="检查配置",exact=True).click()
    expect(page.get_by_text("配置路径就绪",exact=True)).to_be_visible()
    expect(page.get_by_text("运行状态：未测试",exact=True)).to_be_visible()
    page.get_by_label("源码目录",exact=True).fill(str(fixture_dir / "missing"))
    expect(page.get_by_role("button",name="请先保存配置",exact=True)).to_be_disabled()
    expect(page.get_by_text("配置路径就绪",exact=True)).to_have_count(0)
    record("Real project persists; static check never executes Agent; unsaved edits invalidate result")

    response=page.request.get(BASE+"/api/v1/projects").json()
    project=next(item for item in response["items"] if item["name"]==PROJECT_NAME)
    endpoint=BASE+"/api/v1/projects/"+project["id"]+"/agent"
    registration=page.request.get(endpoint).json()
    payload={key:registration[key] for key in ["name","source_path","python_executable","entrypoint"]}
    payload["config"]={"max_tokens":256}
    assert page.request.put(endpoint,data=payload).status==200
    page.reload(wait_until="networkidle")
    page.get_by_role("button",name=PROJECT_NAME,exact=True).click()
    expect(page.get_by_label("智能体名称",exact=True)).to_have_value("Static check fixture")
    page.get_by_role("button",name="保存智能体",exact=True).click()
    expect(page.get_by_text("智能体配置已保存。",exact=True)).to_be_visible()
    assert page.request.get(endpoint).json()["config"]=={"max_tokens":256}
    record("Saving through UI preserves existing model config")

    page.goto(BASE+"/settings",wait_until="networkidle")
    expect(page.get_by_text("sqlite · WAL",exact=True)).to_be_visible()
    record("Settings reports real API and SQLite WAL capability")

    page.route("**/api/v1/projects",lambda route:route.abort())
    page.goto(BASE+"/projects",wait_until="networkidle")
    expect(page.locator('.error[role="alert"]')).to_contain_text("无法连接本地 API")
    page.unroute("**/api/v1/projects")
    page.get_by_role("button",name="重试",exact=True).click()
    expect(page.get_by_role("button",name=PROJECT_NAME,exact=True)).to_be_visible()
    record("API failure state provides a working retry")

    for width,height in [(1440,1000),(768,1024),(390,844)]:
        page.set_viewport_size({"width":width,"height":height})
        page.goto(BASE+"/evaluations/example-candidate?mode=example&case=case-002",wait_until="networkidle")
        expect(page.get_by_role("heading",name="候选运行",exact=True)).to_be_visible()
        overflow=page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not overflow,f"Page overflow at {width}px"
        page.screenshot(path=str(OUT / f"evaluation-{width}.png"),full_page=True)
    record("Desktop, tablet and narrow layouts contain horizontal overflow")
    assert not console_errors,console_errors
    record("No uncaught browser application errors")
    browser.close()

(OUT / "results.json").write_text(json.dumps({"checks":results,"count":len(results),"evaluation_runs_executed":0},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"passed":len(results),"evaluation_runs_executed":0}),flush=True)
