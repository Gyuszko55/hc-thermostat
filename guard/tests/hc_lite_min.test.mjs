// 0.80.0: the compact hc_lite.min.js (what goes to the relay) passes the same tests as hc_lite.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("the compact script passes every HC Lite test", () => {
  const files = ["hc_lite.test.mjs", "hc_lite_cool.test.mjs", "hc_lite_presets.test.mjs", "hc_lite_review.test.mjs"].map((f) => fileURLToPath(new URL(f, import.meta.url)));
  const r = spawnSync(process.execPath, ["--test", ...files], { env: { ...process.env, HC_LITE_MIN: "1" }, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout.slice(-3000));
});
