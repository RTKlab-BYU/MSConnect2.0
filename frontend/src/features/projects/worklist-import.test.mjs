import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { URL } from "node:url";

import { parseWorklistText, validateWorklistTags } from "./worklist-import.ts";

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

test("accepts a bracket marker and finds vendor headers after preamble rows", () => {
  const examples = [
    "Bracket Type=4,,,,,\nSample Type,File Name,Path,Instrument Method,Position,Inj Vol\nSample,run_01,ExampleData,Method,A1,2\n",
    "0,,,,,\nExample sequence,,,,,\nSample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,run_01,ExampleData,Method,A1,2\n",
  ];
  for (const example of examples) {
    const rows = parseWorklistText(example);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].expected_filename, "run_01");
    assert.equal(rows[0].position, 1);
    assert.equal(rows[0].metadata?.source_format, "vendor_ms_worklist");
  }
});

test("unknown vendor rows are tagged in the worklist preview before import", () => {
  const [row] = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,run_01,ExampleData,Method,A1,2\n",
  );
  assert.equal(validateWorklistTags([row]), "run_01: select the sample role in the worklist preview.");
  const tagged = {
    ...row,
    metadata: { ...row.metadata, role_confirmed: true, sample_type: "Plasma" },
  };
  assert.equal(validateWorklistTags([tagged]), "");
});

test("blank and QC roles require their metadata in the worklist preview", () => {
  const rows = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nBlank,blank_01,ExampleData,Method,A1,2\nQC,qc_01,ExampleData,Method,A2,2\n",
  );
  assert.match(validateWorklistTags(rows), /blank type/i);
  rows[0].metadata.blank_type = "solvent";
  assert.match(validateWorklistTags(rows), /QC stage and material/i);
  rows[1].metadata.qc_stage = "sample_preparation";
  rows[1].metadata.qc_material = "Pooled digest";
  assert.equal(validateWorklistTags(rows), "");
});

test("in-app role edits support samples, blanks, prep QC, and filename-tagged HYE pairs", () => {
  const rows = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,sample_01,ExampleData,Method,A1,2\nUnknown,blank_01,ExampleData,Method,A2,2\nUnknown,qc_01,ExampleData,Method,A3,2\nUnknown,demo_HYE_A_01,ExampleData,Method,A4,2\nUnknown,demo_HYE_B_01,ExampleData,Method,A5,2\n",
  );
  rows[0].metadata.role_confirmed = true;
  rows[0].metadata.sample_type = "Plasma";
  rows[0].condition = "Control";
  rows[1].file_role = "true_blank";
  rows[1].sample_name = "Blank-01";
  rows[1].metadata.role_confirmed = true;
  rows[1].metadata.blank_type = "solvent";
  rows[2].file_role = "qc";
  rows[2].sample_name = "Prep-QC-01";
  rows[2].metadata.role_confirmed = true;
  rows[2].metadata.qc_stage = "sample_preparation";
  rows[2].metadata.qc_material = "Pooled digest";

  assert.deepEqual(rows.map((row) => row.file_role), ["sample", "true_blank", "qc", "hye", "hye"]);
  assert.equal(validateWorklistTags(rows), "");
  assert.equal(rows[0].metadata.sample_type, "Plasma");
  assert.equal(rows[1].metadata.blank_type, "solvent");
  assert.equal(rows[2].metadata.qc_stage, "sample_preparation");
  assert.equal(rows[3].qc_program, "hye");
});

test("imports LC vendor worklists and recognizes HYE rows", () => {
  const example = readFileSync(new URL("../../../public/worklist-examples/example-lc-worklist-format.csv", import.meta.url), "utf8");
  const rows = parseWorklistText(example, "lc");
  assert.equal(rows.length, 3);
  assert.equal(rows[0].metadata?.source_format, "vendor_lc_worklist");
  assert.equal(rows[0].metadata?.instrument_worklist_type, "lc");
  assert.equal(rows[1].file_role, "hye");
  assert.equal(rows[1].qc_program, "hye");
  assert.equal(rows[1].sample_name, "HYE-A");
});

test("anonymized MS and LC sequence examples have matching runs and metadata references", () => {
  for (const stem of ["hye", "blank", "preamble"]) {
    const ms = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-ms.csv`, import.meta.url), "utf8");
    const lc = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-lc.csv`, import.meta.url), "utf8");
    const tags = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-tags.csv`, import.meta.url), "utf8");
    const msRows = parseWorklistText(ms, "ms");
    const lcRows = parseWorklistText(lc, "lc");

    assert.deepEqual(msRows.map((row) => row.expected_filename), lcRows.map((row) => row.expected_filename));
    assert.match(tags, /expected_filename,sample_name,file_role/);
    assert.match(tags, /sample_type|blank_type|qc_stage/);
  }
});
