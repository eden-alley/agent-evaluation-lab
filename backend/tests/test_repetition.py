"""Observable repetition classification without model or scorer execution."""
from copy import deepcopy

from lab.comparisons import repetition


def sample(tool="read_file", args=None):
    args = args or {"path": "cli.py"}
    events = [{"event_id": 1, "type": "task_started", "files": {"cli.py": "same"}}]
    for n, cid in enumerate(["first", "second"]):
        events += [{"event_id": 2+n*2, "type": "tool_call", "call_id": cid, "tool": tool,
                    "arguments": args, "files": {"cli.py": "same"}},
                   {"event_id": 3+n*2, "type": "tool_result", "call_id": cid, "tool": tool,
                    "ok": True, "data": "same result", "files": {"cli.py": "same"}}]
    events += [{"event_id": 6, "type": "final_response", "files": {"cli.py": "same"}}]
    requests = [{"case": "U05", "number": 1, "kind": "request", "payload": {"messages": [
        {"role": "tool", "tool_call_id": "first", "content": '{"ok":true,"data":"same result"}'}]}},
        {"case": "U05", "number": 1, "kind": "response", "body": {"choices": [{"message": {"tool_calls": [{"id": "second"}]}}]}},
        {"case": "U05", "number": 2, "kind": "request", "payload": {"messages": [
        {"role": "tool", "tool_call_id": "second", "content": '{"ok":true,"data":"same result"}'}]}}]
    return events, requests


def run(events, rows):
    return repetition.analyze(events, repetition.request_index(rows).get("U05", {}))


def test_identical_read_is_useless_only_with_actual_model_input():
    events, rows = sample()
    result = run(events, rows)
    assert (result["candidate_count"], result["useless"], result["necessary"], result["insufficient"]) == (1,1,0,0)
    assert result["items"][0]["event_id"] == 4
    missing = run(events, [])
    assert missing["useless"] == 0 and missing["insufficient"] == 1


def test_model_response_without_disk_snapshot_does_not_hide_known_file_state():
    events, rows = sample()
    for e in events[3:]: e["event_id"] += 1
    events.insert(3,{"event_id":4,"type":"model_response"})
    assert run(events,rows)["useless"] == 1


def test_cleared_context_is_necessary_and_another_cases_request_is_not_evidence():
    events, rows = sample()
    rows[0]["payload"]["messages"][0]["content"] = "[旧工具结果已清理，如需要请重新调用工具]"
    assert run(events, rows)["necessary"] == 1
    rows[0]["case"] = "other-task"
    assert run(events, rows)["insufficient"] == 1


def test_cleanup_marker_inside_a_visible_tool_result_is_not_context_loss():
    import json
    events,rows=sample(); marker="[旧工具结果已清理，如需要请重新调用工具]"
    for e in events:
        if e['type']=='tool_result':e['data']=marker
    for row in (rows[0],rows[2]):row['payload']['messages'][0]['content']=json.dumps({'ok':True,'data':marker},ensure_ascii=False)
    assert run(events,rows)['useless']==1


def test_changed_test_inputs_justify_retry_even_when_output_is_equal():
    events, rows = sample("run_shell", {"command": '"python.exe" -B -m unittest discover -s tests -v 2>&1'})
    for e in events: e["files"]["tests/test_contract.py"] = "old" if e["event_id"] < 4 else "new"
    assert run(events, rows)["necessary"] == 1
    events, rows = sample("run_shell", {"command": '"python.exe" -B _tmp_e2e.py default 2>&1'})
    for e in events: e["files"]["_tmp_e2e.py"] = "old" if e["event_id"] < 4 else "new"
    assert run(events, rows)["necessary"] == 1


def test_unsupported_commands_and_incomplete_trace_are_not_passing_zero():
    events, rows = sample("run_shell", {"command": "some-command"})
    assert run(events, rows)["insufficient"] == 1
    assert run(events[:-1], rows)["status"] == "incomplete"


def test_three_occurrences_count_two_and_file_change_then_restore_is_not_useless():
    events, rows = sample()
    third = deepcopy(events[3:5])
    for e in third: e["event_id"] += 2; e["call_id"] = "third"
    events = events[:-1]+third+[{"event_id":8,"type":"final_response","files":{"cli.py":"same"}}]
    assert run(events, rows)["candidate_count"] == 2
    events, rows = sample()
    events[2]["files"]["cli.py"] = "changed-then-restored"
    assert run(events, rows)["useless"] == 0


def test_restarted_event_ids_keep_real_source_line_numbers_for_unknown_evidence():
    events, rows = sample()
    events[3]["event_id"] = 2
    events[4]["event_id"] = 3
    source = {"id": "trace", "path": "events.jsonl", "source": "baseline",
              "case_id": "U05", "sha256": "pinned", "kind": "archive"}
    result = repetition.analyze(events, repetition.request_index(rows)["U05"], source)
    assert result["status"] == "incomplete" and result["insufficient"] == 1
    refs = {e["label"]: e for e in result["items"][0]["evidence"]}
    assert refs["前次调用"]["start_line"] == 2
    assert refs["本次原样重复调用"]["start_line"] == 4
    assert refs["前次实际反馈"]["start_line"] == 3
    assert refs["本次实际反馈"]["start_line"] == 5
