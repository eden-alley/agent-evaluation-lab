"""Prepare, read and submit an archived capability review. No model/scorer runner."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from lab.comparisons.review import submission, analyst_materials
from lab.comparisons.review_schemas import Analysis, ReviewSubmission


class ReviewClientError(Exception):
    pass


class Client:
    def __init__(self, base=None, timeout=120):
        base = (base or os.environ.get("LAB_API_URL", "http://127.0.0.1:8100")).rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ReviewClientError("服务地址必须是本机 HTTP 根地址。")
        self.http = httpx.Client(base_url=base + "/api/v1", timeout=timeout, trust_env=False, follow_redirects=False,
                                 headers={"X-Lab-Client": "capability-review-cli", "X-Lab-Tool": "submit_capability_review"})

    def close(self):
        self.http.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ReviewClientError("请求超时，提交状态尚未确认。保留 packet、analysis 和 request 文件，用相同输入重试以取回同一回执；程序不会自动重试。") from exc
        except httpx.HTTPError as exc:
            raise ReviewClientError("无法连接本地平台，请检查服务地址；程序没有自动重试。") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise ReviewClientError(f"平台返回非 JSON（HTTP {response.status_code}）；提交状态待核对，不要另造提交编号。") from exc
        if not response.is_success:
            error = body.get("error", body.get("detail", body))
            raise ReviewClientError(f"HTTP {response.status_code}: {json.dumps(error, ensure_ascii=False)}")
        return body


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def markdown(packet, report=None):
    table = report["metric_report"] if report else packet["metric_report"]
    lines = ["# 当前指标变化", "", (report or {}).get("summary", "程序只读归并现有判据，不重新评分。"), "",
             "| 指标 | A | B | 方向 | 改善题 | 退步题 |", "| --- | --- | --- | --- | --- | --- |"]
    for m in table["quality"]:
        n = m["paired_cases"]
        values = [f"{m[k]}/{n}" if n else "无法判断" for k in ("before", "after")]
        label = {"improved": "本次进步", "regressed": "本次退步", "mixed": "有取舍", "unchanged": "本次无明确变化", "insufficient": "无法判断"}[m['direction']]
        if m['direction'] == 'improved' and m['regressed_cases']:
            label = "净进步（有回归）"
        if m['direction'] == 'regressed' and m['improved_cases']:
            label = "净退步（有改善）"
        lines.append(f"| {m['name']} | {values[0]} | {values[1]} | {label} | {'、'.join(m['improved_cases']) or '无'} | {'、'.join(m['regressed_cases']) or '无'} |")
    lines += ["", "| 资源与计数 | A | B | 变化 |", "| --- | --- | --- | --- |"]
    for m in table["resources"]:
        delta = m["relative_change_pct"]
        change = f"{delta:+.1f}%" if delta is not None else "无法计算相对变化"
        lines.append(f"| {m['name']} | {m['before']} | {m['after']} | {change} |")
    lines += ["", "未评估维度：", ""] + [f"- {m['name']}：{m['reason']}" for m in table["unassessed"]]
    if report:
        lines += ["", "开发建议：", ""]
        for i, r in enumerate(report["recommendations"], 1):
            lines += [f"{i}. **{r['title']}**：{r['action']}", f"   验证：{r['validation']}", ""]
    lines += ["", "读取条件：", ""] + ["- " + s for s in table["limits"]]
    return "\n".join(lines) + "\n"


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-url")
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("comparison_id"); prep.add_argument("--out", type=Path, required=True)
    read = sub.add_parser("read"); read.add_argument("comparison_id"); read.add_argument("--case", required=True)
    read.add_argument("--side", choices=("baseline", "candidate"), required=True); read.add_argument("--path", required=True)
    read.add_argument("--start", type=int, default=1); read.add_argument("--lines", type=int, default=40)
    files = sub.add_parser("files"); files.add_argument("comparison_id"); files.add_argument("--case", required=True)
    files.add_argument("--side", choices=("baseline", "candidate"), required=True); files.add_argument("--query", default="")
    files.add_argument("--offset", type=int, default=0); files.add_argument("--limit", type=int, default=50)
    submit = sub.add_parser("submit"); submit.add_argument("--packet", type=Path, required=True); submit.add_argument("--analysis", type=Path, required=True)
    submit.add_argument("--origin", choices=("external_agent", "manual", "offline_program"), default="external_agent")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    client = None
    try:
        client = Client(args.api_url)
        if args.command == "prepare":
            base = "/comparisons/" + quote(args.comparison_id, safe="")
            verification = client.request("POST", base + "/verify")
            if verification["source_state"] != "unchanged":
                raise ReviewClientError("原归档变化，不能准备新的有效对照；历史报告仍可查看。")
            packet = client.request("GET", base + "/review-materials")
            save(args.out / "packet.json", packet)
            save(args.out / "materials.json", analyst_materials(packet))
            for case in packet["metric_report"]["cases"]:
                save(args.out / "cases" / (quote(case["case_id"], safe="") + ".json"), case)
            save(args.out / "analysis-format.json", Analysis.model_json_schema())
            template = {"summary": "", "recommendations": [], "limitations": []}
            if not (args.out / "analysis.json").exists():
                save(args.out / "analysis.json", template)
            (args.out / "指标升降表.md").write_text(markdown(packet), encoding="utf-8")
            (args.out / "材料摘要.md").write_text(markdown(packet) + "\n机器材料包由程序管理。优先读取 materials.json；需要题面和检查理由时读取 cases/<题号>.json，再按需补读原始文件。\n", encoding="utf-8")
            print(json.dumps({"packet": str(args.out / "packet.json"), "analysis": str(args.out / "analysis.json"),
                              "model_calls": 0, "evaluation_runs": 0}, ensure_ascii=False))
        elif args.command == "files":
            data = client.request("GET", "/comparisons/" + quote(args.comparison_id, safe="") + "/review-catalog",
                params={"case_id": args.case, "side": args.side, "query": args.query, "offset": args.offset, "limit": args.limit})
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "read":
            data = client.request("GET", "/comparisons/" + quote(args.comparison_id, safe="") + "/review-material",
                params={"case_id": args.case, "side": args.side, "path": args.path, "start_line": args.start, "line_count": args.lines})
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            packet = json.loads(args.packet.read_text(encoding="utf-8-sig"))
            analysis = Analysis.model_validate_json(args.analysis.read_text(encoding="utf-8-sig"))
            payload = ReviewSubmission.model_validate(submission(packet, analysis.model_dump(), args.origin)).model_dump()
            save(args.packet.parent / "request.json", payload)
            report = client.request("POST", "/comparisons/" + quote(packet["comparison_id"], safe="") + "/review", json=payload)
            save(args.packet.parent / "report.json", report)
            receipt = {"comparison_id": packet["comparison_id"], "report_id": report["id"], "request_id": payload["request_id"],
                       "report_hash": report["report_hash"], "source_state": report["source_state"],
                       "url": "http://127.0.0.1:3100/comparison?comparison=" + quote(packet["comparison_id"], safe="")}
            save(args.packet.parent / "receipt.json", receipt)
            (args.packet.parent / "指标升降表.md").write_text(markdown(packet, report), encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except (ReviewClientError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
