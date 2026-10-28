import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { URL } from "node:url";

import { parseWorklistText } from "./worklist-import.ts";

test("imports the redacted real-format MS example and tags HYE pairs", () => {
  const example = readFileSync(new URL("../../../public/worklist-examples/example-ms-worklist.csv", import.meta.url), "utf8");
  const rows = parseWorklistText(example);
  assert.equal(rows.length, 362);
  assert.equal(rows[0].position, 1);
  assert.equal(rows[0].metadata?.source_format, "vendor_ms_worklist");
  const hyeRows = rows.filter((row) => row.qc_program === "hye");
  assert.ok(hyeRows.length > 0);
  assert.ok(hyeRows.every((row) => row.file_role === "hye" && row.hye_pair_label));
  const pairs = new Map();
  hyeRows.forEach((row) => pairs.set(row.hye_pair_label, [...(pairs.get(row.hye_pair_label) ?? []), row.sample_name]));
  assert.ok([...pairs.values()].every((mixes) => mixes.length === 2 && mixes.includes("HYE-A") && mixes.includes("HYE-B")));
});

test("rejects worklists with missing required columns or duplicate positions", () => {
  assert.throws(() => parseWorklistText("name,condition\nA,control\n"), /Required columns are missing/);
  assert.throws(() => parseWorklistText("position,sample_name,expected_filename\n1,A,a.raw\n1,B,b.raw\n"), /positions must be unique/);
});

test("accepts the generator's bracket marker before the vendor header", () => {
  const rows = parseWorklistText("Bracket Type=4,,,,,\nSample Type,File Name,Path,Instrument Method,Position,Inj Vol\nSample,run_01,ExampleData,Method,A1,2\n");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].expected_filename, "run_01");
  assert.equal(rows[0].position, 1);
  assert.equal(rows[0].metadata?.source_format, "vendor_ms_worklist");
});

test("imports LC vendor worklists as LC while preserving vendor sample roles", () => {
  const example = readFileSync(new URL("../../../public/worklist-examples/example-lc-worklist-format.csv", import.meta.url), "utf8");
  const rows = parseWorklistText(example, "lc");
  assert.equal(rows.length, 3);
  assert.equal(rows[0].metadata?.source_format, "vendor_lc_worklist");
  assert.equal(rows[0].metadata?.instrument_worklist_type, "lc");
  assert.equal(rows[1].file_role, "hye");
  assert.equal(rows[1].qc_program, "hye");
  assert.equal(rows[1].sample_name, "HYE-A");
});
