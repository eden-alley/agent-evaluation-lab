"""Aggregate already judged checks. This script does not grade Agent behavior.

Usage: python aggregate_scores.py checks.json
Output: JSON on stdout. Standard library only; input is never modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP

UNKNOWN = "unknown"


def percent(numerator, denominator):
    if denominator == 0:
        return UNKNOWN
    return float((Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def summary(checks, *, dimension):
    active = [item for item in checks if item["applicable"]]
    passed = sum(item["result"] == 1 for item in active)
    failed = sum(item["result"] == 0 for item in active)
    unknown = sum(item["result"] == UNKNOWN for item in active)
    total, known = len(active), passed + failed
    verdict = 0 if failed else UNKNOWN if unknown or not total else 1
    result = {
        "satisfied": passed, "not_satisfied": failed, "unknown": unknown,
        "applicable_count": total, "excluded_count": len(checks) - total,
        "decision_coverage_percent": percent(known, total),
        "known_item_pass_rate_percent": percent(passed, known),
        "result": "not_applicable" if dimension and not total else verdict,
        "failed_check_ids": [item["id"] for item in active if item["result"] == 0],
        "unknown_check_ids": [item["id"] for item in active if item["result"] == UNKNOWN],
    }
    if dimension:
        result["score_percent"] = "not_applicable" if not total else UNKNOWN if unknown else percent(passed, total)
    elif not total:
        result["reason"] = "no_applicable_task_requirements"
    return result


def aggregate(document):
    if not isinstance(document, dict) or not isinstance(document.get("dimensions"), list) or not document["dimensions"]:
        raise ValueError("Input requires a nonempty dimensions list")
    dimension_ids, check_ids, dimensions, required = set(), set(), [], []
    for dim in document["dimensions"]:
        if not isinstance(dim, dict) or not isinstance(dim.get("id"), str) or not dim["id"].strip():
            raise ValueError("Each dimension requires a nonempty string id")
        if dim["id"] in dimension_ids:
            raise ValueError(f"Duplicate dimension id: {dim['id']}")
        dimension_ids.add(dim["id"])
        checks = dim.get("checks")
        if not isinstance(checks, list):
            raise ValueError(f"Dimension {dim['id']} requires a checks list")
        for item in checks:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                raise ValueError("Each check requires a nonempty string id")
            if item["id"] in check_ids:
                raise ValueError(f"Duplicate check id: {item['id']}; associate shared checks without counting them twice")
            check_ids.add(item["id"])
            if type(item.get("applicable")) is not bool or type(item.get("required_for_task")) is not bool:
                raise ValueError(f"Check {item['id']} requires explicit boolean applicable and required_for_task")
            value = item.get("result")
            if item["applicable"]:
                if not ((type(value) is int and value in (0, 1)) or (type(value) is str and value == UNKNOWN)):
                    raise ValueError(f"Applicable check {item['id']} requires integer 1/0 or string unknown")
            elif value is not None or not isinstance(item.get("excluded_reason"), str) or not item["excluded_reason"].strip():
                raise ValueError(f"Excluded check {item['id']} requires null result and a nonempty excluded_reason")
            if item["required_for_task"]:
                required.append(item)
        dimensions.append({"id": dim["id"], "title": dim.get("title", dim["id"]),
                           "summary": summary(checks, dimension=True),
                           "excluded_checks": [{"id": item["id"], "reason": item["excluded_reason"]} for item in checks if not item["applicable"]]})
    return {
        "rubric_version": document.get("rubric_version"), "run_id": document.get("run_id"),
        "dimensions": dimensions, "task_acceptance": summary(required, dimension=False),
        "overall_weighted_score": None,
        "scope": "Aggregation of supplied labels only. Evidence sufficiency, rubric validity, and semantic judgments are not verified by this script.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="UTF-8 JSON containing dimensions and already judged checks")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8-sig") as stream:
            result = aggregate(json.load(stream))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"Cannot aggregate: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
