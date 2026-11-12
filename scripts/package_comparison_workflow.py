"""Build the platform text bundle from the workflow sources; never publish it."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
METHOD_VERSION = "0.1.1"
sys.path.insert(0, str(ROOT / "backend"))
from lab.comparisons.schemas import CaseAnalysisInput, FinalReportInput
from lab.quality_checks import digest


def build():
    slug = "agent-version-comparison-workflow"
    folder = ROOT / "skills" / slug
    for name, model in (("case-analysis", CaseAnalysisInput), ("final-report", FinalReportInput)):
        (folder / "references" / (name + ".schema.json")).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = ["SKILL.md", "references/platform-protocol.md", "references/engineering-retro.md", "references/u05-baseline-example.md",
             "references/case-analysis.schema.json", "references/final-report.schema.json"]
    text = (folder / files[0]).read_text(encoding="utf-8")
    for name in files[1:]:
        anchor = "resource-" + Path(name).name.replace(".", "-")
        text = text.replace("(" + name + ")", "(#" + anchor + ")")
        content = (folder / name).read_text(encoding="utf-8")
        text += '\n\n<a id="' + anchor + '"></a>\n\n## ' + name + "\n\n"
        text += "```json\n" + content + "```\n" if name.endswith(".json") else content
    # Links inside appended references use the same resource anchors.
    for name in files[1:]:
        anchor = "resource-" + Path(name).name.replace(".", "-")
        text = text.replace("(" + Path(name).name + ")", "(#" + anchor + ")")
    text = text.strip()  # Match the existing SkillContent API's whitespace normalization.
    if len(text) > 50000:
        raise ValueError("Workflow bundle exceeds the existing Skill limit")
    payload = {"content": text, "change_note": f"workflow v{METHOD_VERSION}：融入retro工程复盘，核查已有机制、实际缺口、作用位置及最小动作；评分和接口不变，未进行模型判断校准。"}
    (ROOT / "skills/platform" / (slug + ".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog_path = ROOT / "skills/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entry = {"slug": slug, "method_version": METHOD_VERSION, "catalog": {
        "name": "Agent版本对比与开发方向", "description": f"外部Agent逐题分析已有运行，并核查已有机制、实际缺口和最小动作，提交带证据的开发建议。v{METHOD_VERSION}离线试用。",
        "kind": "evaluation", "tags": ["版本对比", "workflow", "能力变化", "开发方向"]},
        "payload_file": "platform/" + slug + ".json", "platform_content_hash": digest({"content": text}),
        "characters": len(text), "source_files": [{"path": name, "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()} for name in files]}
    catalog["skills"] = [e for e in catalog["skills"] if e["slug"] != slug] + [entry]
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"slug": slug, "characters": len(text), "hash": entry["platform_content_hash"]}))


if __name__ == "__main__":
    build()
