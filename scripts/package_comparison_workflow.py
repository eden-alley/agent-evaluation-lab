"""Build the platform text bundle from the workflow sources; never publish it."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
METHOD_VERSION = "0.2.0"
sys.path.insert(0, str(ROOT / "backend"))
from lab.quality_checks import digest


def build():
    slug = "agent-version-comparison-workflow"
    folder = ROOT / "skills" / slug
    files = ["SKILL.md", "references/engineering-retro.md"]
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
    payload = {"content": text, "change_note": f"轻量分析 v{METHOD_VERSION}：程序准备、统计及一次提交；Skill仅分析事实、取舍与最多3条建议；保留retro核查已有机制的思路，不改原评分。离线验证，模型质量未校准。"}
    (ROOT / "skills/platform" / (slug + ".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog_path = ROOT / "skills/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entry = {"slug": slug, "method_version": METHOD_VERSION, "catalog": {
        "name": "Agent版本对比与开发方向", "description": f"程序准备已有归档和指标表，外部Agent用轻量Skill解释升降、缺陷及最多3条开发建议。v{METHOD_VERSION}离线试用。",
        "kind": "evaluation", "tags": ["版本对比", "轻量Skill", "能力变化", "开发方向"]},
        "payload_file": "platform/" + slug + ".json", "platform_content_hash": digest({"content": text}),
        "characters": len(text), "source_files": [{"path": name, "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()} for name in files]}
    catalog["skills"] = [e for e in catalog["skills"] if e["slug"] != slug] + [entry]
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"slug": slug, "characters": len(text), "hash": entry["platform_content_hash"]}))


if __name__ == "__main__":
    build()
