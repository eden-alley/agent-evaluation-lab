import test from "node:test";
import assert from "node:assert/strict";
import * as comparisons from "../lib/comparisons";

test("opening, switching and refreshing views request only the current view", async () => {
  const calls: string[] = [];
  const get = async (path: string) => {
    calls.push(path);
    return path === "/comparisons" ? { items: [] } : { id: path };
  };
  await comparisons.loadComparisonView("first", get as never);
  await comparisons.loadComparisonView("second", get as never);
  await comparisons.loadComparisonView("second", get as never);
  await comparisons.loadComparisonView("", get as never);
  assert.deepEqual(calls, [
    "/comparisons/first",
    "/comparisons/second",
    "/comparisons/second",
    "/comparisons",
  ]);
});

test("verification text distinguishes absent time, unchanged and changed", () => {
  assert.match(
    comparisons.sourceVerificationText({
      source_state: "unchecked",
      source_checked_at: null,
    }),
    /未记录/,
  );
  assert.doesNotMatch(
    comparisons.sourceVerificationText({
      source_state: "unchecked",
      source_checked_at: null,
    }),
    /已变化/,
  );
  assert.match(
    comparisons.sourceVerificationText({
      source_state: "unchanged",
      source_checked_at: "2026-11-13T01:00:00Z",
    }),
    /未变化/,
  );
  assert.match(
    comparisons.sourceVerificationText({
      source_state: "changed",
      source_checked_at: "2026-11-13T01:00:00Z",
    }),
    /已变化/,
  );
});

test("manual verification posts once while pending and propagates failure without retry", async () => {
  const calls: Array<[string, RequestInit | undefined]> = [];
  let reject!: (error: Error) => void;
  const send = (path: string, init?: RequestInit) => {
    calls.push([path, init]);
    return new Promise((_resolve, fail) => {
      reject = fail;
    });
  };
  const verify = comparisons.createEvidenceVerifier("a/b", send as never);
  const first = verify();
  const second = verify();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/comparisons/a%2Fb/verify");
  assert.equal(calls[0][1]?.method, "POST");
  reject(new Error("offline"));
  await assert.rejects(first, /offline/);
  await assert.rejects(second, /offline/);
  assert.equal(calls.length, 1);
});

test("successful manual verification returns the server result", async () => {
  const result = {
    source_state: "changed",
    source_checked_at: "2026-11-13T01:00:00Z",
    source_state_scope: "last_full_verification",
  };
  const verify = comparisons.createEvidenceVerifier(
    "id",
    (async () => result) as never,
  );
  assert.deepEqual(await verify(), result);
});
