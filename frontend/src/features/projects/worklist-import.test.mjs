import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { URL } from "node:url";

import { applyWorklistAnnotations, parseWorklistAnnotationText, parseWorklistText } from "./worklist-import.ts";

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

test("finds vendor headers after multiple preamble rows", () => {
  const rows = parseWorklistText(
    "0,,,,,\nExample sequence,,,,,\nSample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,run_01,ExampleData,Method,A1,2\n",
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].expected_filename, "run_01");
  assert.equal(rows[0].position, 1);
});

test("requires explicit role annotations for vendor rows marked Unknown", () => {
  const rows = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,run_01,ExampleData,Method,A1,2\n",
  );
  assert.throws(() => applyWorklistAnnotations(rows, null), /unknown vendor sample type/);
});

test("requires blank subtype and QC stage/material for vendor controls", () => {
  const rows = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nBlank,blank_01,ExampleData,Method,A1,2\nQC,qc_01,ExampleData,Method,A2,2\n",
  );
  assert.throws(() => applyWorklistAnnotations(rows, null), /needs a blank_type/i);
  const annotations = parseWorklistAnnotationText(
    "expected_filename,sample_name,file_role,blank_type,qc_stage,qc_material\n" +
      "blank_01,Blank-01,true_blank,solvent,,,\n" +
      "qc_01,Prep-QC-01,qc,,sample_preparation,Pooled digest\n",
  );
  assert.deepEqual(applyWorklistAnnotations(rows, annotations).map((row) => row.file_role), ["true_blank", "qc"]);
});

test("applies sample, blank, prep-QC, and HYE annotations by filename", () => {
  const worklist = parseWorklistText(
    "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\nUnknown,sample_01,ExampleData,Method,A1,2\nUnknown,blank_01,ExampleData,Method,A2,2\nUnknown,qc_01,ExampleData,Method,A3,2\nUnknown,hye_a,ExampleData,Method,A4,2\nUnknown,hye_b,ExampleData,Method,A5,2\n",
  );
  const annotations = parseWorklistAnnotationText(
    "expected_filename,sample_name,file_role,qc_program,hye_pair_label,condition,sample_type,blank_type,qc_stage,qc_material\n" +
      "sample_01,Sample-01,sample,,,Control,Plasma,,,,\n" +
      "blank_01,Blank-01,true_blank,,,,,solvent,,,,\n" +
      "qc_01,Prep-QC-01,qc,,,,Pooled digest,,sample_preparation,Pooled digest\n" +
      "hye_a,HYE-A,hye,hye,HYE-01,,HYE reference material,,,\n" +
      "hye_b,HYE-B,hye,hye,HYE-01,,HYE reference material,,,\n",
  );
  const tagged = applyWorklistAnnotations(worklist, annotations);

  assert.deepEqual(tagged.map((row) => row.file_role), ["sample", "true_blank", "qc", "hye", "hye"]);
  assert.equal(tagged[0].condition, "Control");
  assert.equal(tagged[1].metadata?.blank_type, "solvent");
  assert.equal(tagged[2].metadata?.qc_stage, "sample_preparation");
  assert.equal(tagged[2].metadata?.vendor_sample_type, "Unknown");
  assert.equal(tagged[3].qc_program, "hye");
});

test("rejects incomplete and duplicate annotation maps", () => {
  const worklist = parseWorklistText(
    "sample_name,expected_filename,file_role\nSample-01,sample_01,sample\n",
  );
  const incomplete = parseWorklistAnnotationText("expected_filename,sample_name,file_role\nsample_02,Sample-02,sample\n");
  assert.throws(() => applyWorklistAnnotations(worklist, incomplete), /not found in the MS worklist/);
  assert.throws(
    () => parseWorklistAnnotationText("expected_filename,sample_name,file_role\nsample_01,Sample-01,sample\nsample_01,Sample-02,sample\n"),
    /must be unique/,
  );
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

test("all anonymized paired sequence examples have matching MS, LC, and role metadata", () => {
  for (const stem of ["hye", "blank", "preamble"]) {
    const ms = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-ms.csv`, import.meta.url), "utf8");
    const lc = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-lc.csv`, import.meta.url), "utf8");
    const tags = readFileSync(new URL(`../../../public/worklist-examples/example-sequence-${stem}-tags.csv`, import.meta.url), "utf8");
    const msRows = applyWorklistAnnotations(parseWorklistText(ms, "ms"), parseWorklistAnnotationText(tags));
    const lcRows = applyWorklistAnnotations(parseWorklistText(lc, "lc"), parseWorklistAnnotationText(tags), { requireFullMatch: false });

    assert.deepEqual(msRows.map((row) => row.expected_filename), lcRows.map((row) => row.expected_filename));
    assert.ok(msRows.every((row) => row.metadata?.annotation_source === "worklist_annotation_csv"));
  }
});
