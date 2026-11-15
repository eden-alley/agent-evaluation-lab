from collections import defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path
import sys


def records(directory, table):
    with (directory / (table + ".csv")).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def reconcile(directory):
    orders = {row["order_id"]: row for row in records(directory, "orders")}
    duplicates, conflicts, unmatched = [], [], []
    seen_settlements = {}
    gross, refunds = defaultdict(Decimal), defaultdict(Decimal)

    for table in ("settlements", "reversals"):
        by_id = defaultdict(list)
        for row in records(directory, table):
            by_id[row["id"]].append(row)
        for identifier, entries in by_id.items():
            row = entries[0]
            key = {"table": table, "id": identifier}
            if any(entry != row for entry in entries[1:]):
                conflicts.append(key)
                continue
            if len(entries) > 1:
                duplicates.append({**key, "extra_rows": len(entries) - 1})
            order_id = row["order_id"]
            order = orders.get(order_id)
            reason = None
            if order is None:
                reason = "unknown_order"
            elif row["currency"] != order["currency"]:
                reason = "currency_mismatch"
            elif table == "reversals":
                original = seen_settlements.get(row["settlement_id"])
                if original is None:
                    reason = "unmatched_settlement"
                elif original["order_id"] != order_id:
                    reason = "order_mismatch"
            if reason:
                unmatched.append({**key, "reason": reason})
                continue
            amount = Decimal(row["amount"])
            if table == "settlements":
                seen_settlements[identifier] = row
                gross[order_id] += amount
            else:
                refunds[order_id] += amount

    rows = []
    for order_id, order in orders.items():
        expected = Decimal(order["expected_amount"])
        net = gross[order_id] - refunds[order_id]
        rows.append({"order_id": order_id, "expected": expected, "gross": gross[order_id],
                     "reversal": refunds[order_id], "net": net, "difference": net - expected})
    money = ("expected", "gross", "reversal", "net", "difference")
    totals = {key: sum(row[key] for row in rows) for key in money}
    matched_orders = {row["order_id"] for row in seen_settlements.values()}
    for row in rows + [totals]:
        row.update({key: format(row[key], ".2f") for key in money})
    return {"orders": rows, "totals": totals, "duplicate_rows": duplicates,
            "conflicting_ids": conflicts, "unmatched": unmatched,
            "unmatched_order_ids": sorted(orders.keys() - matched_orders)}


if __name__ == "__main__":
    source, output = map(Path, sys.argv[1:])
    output.write_text(json.dumps(reconcile(source), ensure_ascii=False, indent=2), encoding="utf-8")
