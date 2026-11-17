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
    def __init__(self, message, *, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    @property
    def definite_rejection(self):
        # A timeout, malformed response or server failure may follow a commit.
        return self.status_code is not None and 400 <= self.status_code < 500 and self.status_code != 408


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
            error = body.get("error", body.get("detail", body)) if isinstance(body, dict) else body
            raise ReviewClientError(f"HTTP {response.status_code}: {json.dumps(error, ensure_ascii=False)}",
                                    status_code=response.status_code, response_body=body)
        return body


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def markdown(packet, report=None):
    table = report["metric_report"] if report else packet["metric_report"]
    repeat_details = []
    lines = ["# 当前指标变化", "", (report or {}).get("summary", "程序只读归并现有判据，不重新评分。"), "",
             "| 指标 | A | B | 方向 | 改善题 | 退步题 |", "| --- | --- | --- | --- | --- | --- |"]
    policy = (report or packet).get('review_policy')
    if policy:
        lines[3:3] = [f"分析用途：{policy['label']}（{policy['case_count']}题）。", '']
    for m in table["quality"]:
        n = m["paired_cases"]
        values = [f"{m[k]}/{n}" if n else "无法判断" for k in ("before", "after")]
        label = {"improved": "本次进步", "regressed": "本次退步", "mixed": "有取舍", "unchanged": "本次无明确变化", "insufficient": "无法判断"}[m['direction']]
        if m['direction'] == 'improved' and m['regressed_cases']:
            label = "净进步（有回归）"
        if m['direction'] == 'regressed' and m['improved_cases']:
            label = "净退步（有改善）"
        lines.append(f"| {m['name']} | {values[0]} | {values[1]} | {label} | {'、'.join(m['improved_cases']) or '无'} | {'、'.join(m['regressed_cases']) or '无'} |")
    process=table.get("repetition")
    if process:
        direction={"improved":"本次进步","regressed":"本次退步","mixed":"有取舍","unchanged":"本次无明确变化","insufficient":"证据不足"}[process['direction']]
        lines += ["", "| 过程指标 | A | B | 方向 |", "| --- | --- | --- | --- |",
                  f"| {process['name']} | {process['before'] if process['before'] is not None else '无法判断'} | {process['after'] if process['after'] is not None else '无法判断'} | {direction} |",
                  "", "跨工具等价重复：未评估。次数越少越好，不因总调用变多导致占比下降就判进步。"]
        if report:
            repeat_details = ['', '<details>', '<summary>原样重复判定明细</summary>', '']
            for row in process['cases']:
                for side in ('baseline','candidate'):
                    data=row[side]
                    if not data: continue
                    repeat_details += ["",f"## {row['case_id']} · {'A' if side=='baseline' else 'B'} 原样重复判定", "",
                              f"候选{data['candidate_count']}，必要{data['necessary']}，确认无效{data['useless']}，证据不足{data['insufficient']}。"]
                    for item in data['items']:
                        label={'necessary':'必要重复','useless':'无效重复','insufficient':'证据不足'}[item['classification']]
                        repeat_details += ["",f"- 事件{item['event_id']}（前次{item['previous_event_id']}）：{label}。{item['reason']}"]
                        repeat_details += [f"  - {e['label']}：{e['path']}，第{e['start_line']}行" for e in item['evidence']]
            repeat_details += ['', '</details>']
    lines += ["", "| 资源与计数 | A | B | 变化 |", "| --- | --- | --- | --- |"]
    for m in table["resources"]:
        delta = m["relative_change_pct"]
        change = f"{delta:+.1f}%" if delta is not None else "无法计算相对变化"
        lines.append(f"| {m['name']} | {m['before']} | {m['after']} | {change} |")
    lines += ["", "未评估维度：", ""] + [f"- {m['name']}：{m['reason']}" for m in table["unassessed"]]
    if report:
        if report['recommendations']:
            lines += ["", "## 下一步开发建议", ""]
        for i, r in enumerate(report["recommendations"], 1):
            lines += [f"{i}. **{r['title']}**：{r['action']}", f"   优先理由：{r.get('priority_reason') or '本报告未单独记录。'}", f"   验证：{r['validation']}", ""]
        for case in report.get("case_analyses", []):
            explanation = case["content"].get("explanation")
            if not explanation:
                continue
            focus = {"baseline": "A运行", "candidate": "B运行", "comparison": "A/B对照"}[explanation["focus"]]
            lead, *acceptance = explanation['result']['text'].split('\n\n')
            lines += ["", f"## {case['case_id']} 任务过程讲解 · {focus}", "", '**' + lead + '**', '', explanation["background"], ""]
            for stage in explanation["stages"]:
                lines += [f"### {stage['title']}", "", stage["text"], ""]
                for e in stage["evidence"]:
                    location = f"事件{e['event_id']}" if e.get("event_id") else f"检查项{e['check_id']}" if e.get("check_id") else f"第{e['start_line']}行起"
                    if e.get('model_reply'): location += f" · 第{e['model_reply']}次模型回复"
                    lines.append(f"- 依据：{'A' if e['source']=='baseline' else 'B'} · {e['path']} · {location}")
            lines += ['', '### 最终验收', '', '\n\n'.join(acceptance)]
            for e in explanation['result']['evidence']:
                locator = f"事件{e['event_id']}" if e.get('event_id') else f"检查项{e['check_id']}" if e.get('check_id') else f"第{e['start_line']}行起"
                lines.append(f"- 结果依据：{'A' if e['source']=='baseline' else 'B'} · {e['path']} · {locator}")
            lines += ["", *["- 讲解限制：" + s for s in explanation["limitations"]]]
    method = (report or packet).get("skill_delivery")
    if method:
        skill = method["skill"]
        lines += ["", "## 本次提供的方法", "", f"{skill['name']} · {skill.get('method_version') or skill['version_id']}",
                  "", f"版本：{skill['version_id']}；提供记录：{method['id']}；提供时间：{method['provided_at']}",
                  "", "方法正文由程序提供；分析者阅读和模型遵循未验证。"]
    if report and report.get("output_checks"):
        lines += ["", "输出检查：结构与引用通过；语义与模型遵循未验证。"]
        for i, r in enumerate(report["recommendations"], 1):
            lines += ["", f"建议{i}的直接依据："]
            for e in r.get("evidence", []):
                locator = f"事件{e['event_id']}" if e.get("event_id") else f"检查项{e['check_id']}" if e.get("check_id") else f"第{e['start_line']}行"
                lines.append(f"- {e['case_id']} · {e['source']} · {e['path']} · {locator}")
    lines += ["", "读取条件：", ""] + ["- " + s for s in table["limits"]]
    lines += repeat_details
    return "\n".join(lines) + "\n"


def material_summary(packet):
    method = packet['skill_delivery']
    required = '、'.join(method['requirements']['explanation_case_ids']) or '无额外指定'
    lines = [markdown(packet), '\n先读取 Skill正文.md。', f'明确指定必须讲解：{required}。']
    if 'key_case_candidates' in packet:
        lines += ['\n关键题候选（按需选代表，不要求逐题讲满）：']
        lines += [f"- {c['case_id']}：{'；'.join(c['reasons'])}" for c in packet['key_case_candidates']]
        lines += ['建议引用题必须讲清回复区间、动作、反馈和关键转折；其余题保留全量统计和原判据。']
    policy = packet.get('review_policy')
    guidance = '仅提交指标与关键过程，不生成开发建议。' if policy and not policy['recommendations_allowed'] else '可附整批开发建议；没有建议也不必解释原因。提供时须引用题目原件。'
    lines += [guidance,
              '程序管理材料与提交。按需读 cases/<题号>.json，再补读原始文件；不用通读全部轨迹。']
    return '\n'.join(lines) + '\n'


def prepare_review_files(client, comparison_id, out, *, review_scope='focused', explain_case_ids=None):
    """Persist one fixed preparation; never silently issue another delivery on resume."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    request = {'explain_case_ids': explain_case_ids, 'review_scope': review_scope}
    request_path = out / 'preparation-request.json'
    if request_path.exists() and json.loads(request_path.read_text(encoding='utf-8-sig')) != request:
        raise ValueError('准备参数已固定；不能在同一交付目录更换用途或讲解题。')
    packet_path = out / 'packet.json'
    if packet_path.exists():
        packet = json.loads(packet_path.read_text(encoding='utf-8-sig'))
        if packet['comparison_id'] != comparison_id:
            raise ValueError('已有材料属于另一份对比。')
    else:
        if (out / 'preparation-attempt.json').exists():
            raise ReviewClientError('准备响应尚未确认。保留原请求；请找回原 packet，程序不会自动再次 prepare。')
        save(request_path, request)
        save(out / 'preparation-attempt.json', {'comparison_id': comparison_id, 'state': 'response_pending'})
        packet = client.request('POST', '/comparisons/' + quote(comparison_id, safe='') + '/review-materials', json=request)
        save(packet_path, packet)
    save(out / 'materials.json', analyst_materials(packet))
    method = packet['skill_delivery']
    save(out / '方法提供记录.json', method)
    (out / 'Skill正文.md').write_text(method['skill']['content'], encoding='utf-8')
    for case in packet['metric_report']['cases']:
        save(out / 'cases' / (quote(case['case_id'], safe='') + '.json'), case)
    save(out / 'analysis-format.json', Analysis.model_json_schema())
    if not (out / 'analysis.json').exists():
        template = {'summary': '', 'recommendations': [], 'case_explanations': []}
        if packet.get('review_policy', {}).get('recommendations_allowed') is False:
            template.pop('recommendations')
        save(out / 'analysis.json', template)
    report_path = out / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8-sig')) if report_path.exists() else None
    (out / '指标升降表.md').write_text(markdown(packet, report), encoding='utf-8')
    (out / '材料摘要.md').write_text(material_summary(packet), encoding='utf-8')
    return packet


def submit_review_files(client, packet_path, analysis_path, *, origin='external_agent', frontend_url=None):
    """Submit the original ReviewSubmission again after uncertainty, with fixed inputs."""
    packet_path, analysis_path = Path(packet_path), Path(analysis_path)
    out = packet_path.parent
    packet = json.loads(packet_path.read_text(encoding='utf-8-sig'))
    analysis = Analysis.model_validate_json(analysis_path.read_text(encoding='utf-8-sig'))
    payload = ReviewSubmission.model_validate(submission(packet, analysis.model_dump(), origin)).model_dump()
    request_path = out / 'request.json'
    if request_path.exists():
        original = json.loads(request_path.read_text(encoding='utf-8-sig'))
        if original != payload:
            raise ValueError('提交输入已固定；请保留原 analysis、packet 和 request，不能覆盖待确认请求。')
        payload = original
    else:
        save(request_path, payload)
    # The editable analysis file may later be corrected. Keep the actual submitted
    # analysis beside the immutable request, including for pre-existing requests.
    snapshot_path = out / 'submitted-analysis.json'
    if not snapshot_path.exists():
        save(snapshot_path, payload['analysis'])
    elif json.loads(snapshot_path.read_text(encoding='utf-8-sig')) != payload['analysis']:
        raise ValueError('保存的分析快照与原请求不一致。')
    report_path = out / 'report.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    else:
        rejection_path = out / 'rejection.json'
        if rejection_path.exists():
            rejected = json.loads(rejection_path.read_text(encoding='utf-8-sig'))
            if rejected['request_id'] != payload['request_id']:
                raise ValueError('保存的拒绝记录与原请求不一致。')
            raise ReviewClientError(rejected['message'], status_code=rejected['status_code'],
                                    response_body=rejected['response_body'])
        try:
            report = client.request('POST', '/comparisons/' + quote(packet['comparison_id'], safe='') + '/review', json=payload)
        except ReviewClientError as exc:
            if exc.definite_rejection:
                save(rejection_path, {'request_id': payload['request_id'], 'status_code': exc.status_code,
                                     'response_body': exc.response_body, 'message': str(exc)})
            raise
        if report.get('request_id') != payload['request_id'] or not report.get('id') or not report.get('report_hash'):
            raise ReviewClientError('报告响应与原请求不一致，保留文件等待核对。')
        save(report_path, report)
    if report.get('request_id') != payload['request_id'] or report.get('packet_hash') != payload['packet_hash']:
        raise ValueError('保存的报告与原请求或材料不一致。')
    receipt = {'comparison_id': packet['comparison_id'], 'report_id': report['id'], 'request_id': payload['request_id'],
               'report_hash': report['report_hash'], 'source_state': report['source_state'],
               'url': (frontend_url.rstrip('/') if frontend_url else '') + '/comparison?comparison=' + quote(packet['comparison_id'], safe='')}
    if report.get('skill_delivery'):
        receipt.update(delivery_id=report['skill_delivery']['id'], output_check_status=report['output_checks']['status'])
    receipt_path = out / 'receipt.json'
    if receipt_path.exists() and json.loads(receipt_path.read_text(encoding='utf-8-sig')) != receipt:
        raise ValueError('保存的回执与报告不一致。')
    save(receipt_path, receipt)
    (out / '指标升降表.md').write_text(markdown(packet, report), encoding='utf-8')
    return report, receipt


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-url")
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("comparison_id"); prep.add_argument("--out", type=Path, required=True)
    prep.add_argument('--scope', choices=('focused', 'formal_batch'), default='focused', help='默认小范围验证；正式整批评测选formal_batch，3题及以内始终不附建议')
    prep.add_argument("--explain", dest="explain_case_ids", action="append", help="额外指定必须讲解的题号，可重复；默认按关键题候选选择")
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
            prepare_review_files(client, args.comparison_id, args.out,
                                 review_scope=args.scope, explain_case_ids=args.explain_case_ids)
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
            _, receipt = submit_review_files(client, args.packet, args.analysis, origin=args.origin,
                                             frontend_url='http://127.0.0.1:3100')
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
