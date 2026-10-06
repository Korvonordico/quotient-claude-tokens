// Run: node --test server/test/stats.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { validate, summarize, buildAverage, mayReplace, MAX_BODY, MIN_PUBLISH } from "../src/stats.js";

const good = { v: 1, q: "0.9.0", family: "opus", estimate: 225000, actual: 259000 };
const body = (o) => JSON.stringify(o);

test("a normal job is accepted and only its numbers are kept", () => {
  assert.deepEqual(validate(body(good)), { family: "opus", version: "0.9.0", estimate: 225000, actual: 259000 });
});

test("any extra field is refused, even a harmless one", () => {
  for (const extra of [{ date: "2026-10-05" }, { session: "abc" }, { name: "x" }, { turns: 3 }]) {
    assert.equal(validate(body({ ...good, ...extra })), null);
  }
});

test("a missing field is refused", () => {
  for (const k of Object.keys(good)) {
    const o = { ...good };
    delete o[k];
    assert.equal(validate(body(o)), null);
  }
});

test("wrong types, ranges and families are refused", () => {
  const bad = [
    { v: 2 }, { q: "0.9" }, { q: "x.y.z" }, { q: 9 }, { family: "gpt" }, { family: "Opus" },
    { estimate: 999 }, { estimate: 100000001 }, { estimate: 1500.5 }, { estimate: "225000" },
    { actual: -5 }, { actual: null },
    { estimate: 10000, actual: 110000 }, // ratio 11: implausible
    { estimate: 1000000, actual: 90000 }, // ratio 0.09: implausible
  ];
  for (const change of bad) assert.equal(validate(body({ ...good, ...change })), null, JSON.stringify(change));
});

test("not JSON, an array, empty or too long is refused", () => {
  assert.equal(validate("not json"), null);
  assert.equal(validate("[1,2]"), null);
  assert.equal(validate(""), null);
  assert.equal(validate(" ".repeat(MAX_BODY + 1)), null);
});

const job = (ratio) => ({ estimate: 100000, actual: Math.round(100000 * ratio) });
const many = (ratios, times) => Array.from({ length: times }, () => ratios).flat().map(job);

test("nothing is published below 30 jobs: a single job cannot be read in the file", () => {
  assert.equal(summarize(many([1.1, 1.2, 1.3], 9)), null); // 27 jobs
  assert.equal(buildAverage({ opus: many([1.2], 29) }, many([1.2], 29), "2026-10-06"), null);
  assert.ok(summarize(many([1.1, 1.2, 1.3], 10)));
  assert.equal(MIN_PUBLISH, 30);
});

test("the factor is the median ratio, rounded to 2 decimals", () => {
  const s = summarize(many([1.0, 1.234, 1.5], 10));
  assert.equal(s.factor, 1.23);
  assert.equal(s.jobs, 30);
  assert.deepEqual(Object.keys(s).sort(), ["factor", "jobs", "p25", "p75"]);
});

test("twice too high and twice too low weigh the same", () => {
  assert.equal(summarize(many([0.5, 2], 15)).factor, 1);
});

test("a few false numbers cannot move the average", () => {
  const honest = many([1.1, 1.15, 1.2, 1.25, 1.3], 8);
  const fake = many([9, 9.5, 0.11], 3);
  const s = summarize([...honest, ...fake]);
  assert.equal(s.jobs, 49);
  assert.ok(s.factor >= 1.15 && s.factor <= 1.25, String(s.factor));
});

test("a family is listed only from 30 jobs; all of them count in 'all'", () => {
  const byFamily = { opus: many([1.1, 1.2, 1.3], 10), haiku: many([2, 2.2], 5) };
  const all = [...byFamily.opus, ...byFamily.haiku];
  const avg = buildAverage(byFamily, all, "2026-10-06");
  assert.deepEqual(Object.keys(avg.families), ["opus"]);
  assert.equal(avg.all.jobs, 40);
  assert.equal(avg.schema, 1);
});

test("a big jump needs many new jobs", () => {
  const prev = { all: { factor: 1.2 } };
  assert.equal(mayReplace(prev, { all: { factor: 1.4 } }, 20), true); // +17%
  assert.equal(mayReplace(prev, { all: { factor: 3.0 } }, 20), false); // x2.5 with only 20 new jobs
  assert.equal(mayReplace(prev, { all: { factor: 3.0 } }, 150), true);
  assert.equal(mayReplace(null, { all: { factor: 3.0 } }, 20), true); // the first one
  assert.equal(mayReplace(prev, null, 500), false);
});

test("no jobs: no average, no crash", () => {
  assert.equal(summarize([]), null);
  assert.equal(buildAverage({}, [], "2026-10-06"), null);
});

test("two-digit versions such as 0.10.0 are accepted (the line format does not change)", () => {
  assert.deepEqual(validate(body({ ...good, q: "0.10.0" })), { family: "opus", version: "0.10.0", estimate: 225000, actual: 259000 });
});
