import type { WorklistImportRow } from "@/lib/api/types";

export const roleOptions = ["sample", "qc", "hye", "prtc", "library", "blank", "true_blank", "wash", "calibration"] as const;

export type InstrumentWorklistKind = "lc" | "ms";

export function parseWorklistText(text: string, instrumentKind: InstrumentWorklistKind = "ms"): WorklistImportRow[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) throw new Error("The worklist must include a header row and at least one injection.");
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const normalizeHeader = (header: string) => header.trim().toLowerCase().replace(/\s+/g, " ");
  const headerLine = lines.findIndex((line) => {
    const candidate = parseDelimitedLine(line, delimiter).map(normalizeHeader);
    const hasFilename = candidate.some((header) => ["expected_filename", "expected file", "filename", "file name", "file", "raw file", "raw_file"].includes(header));
    const hasSample = candidate.some((header) => ["sample_name", "sample", "sample id", "sample_id", "name", "sample type"].includes(header));
    return hasFilename && hasSample;
  });
  if (headerLine < 0) throw new Error("Required columns are missing. Include sample_name and expected_filename, or use the vendor MS format with Sample Type and File Name columns.");
  if (headerLine >= lines.length - 1) throw new Error("The worklist has a bracket marker but no column header or injection rows.");
  const headers = parseDelimitedLine(lines[headerLine], delimiter).map(normalizeHeader);
  const hasFilename = headers.some((header) => ["expected_filename", "expected file", "filename", "file name", "file", "raw file", "raw_file"].includes(header));
  const hasSample = headers.some((header) => ["sample_name", "sample", "sample id", "sample_id", "name"].includes(header));
  const vendorFormat = headers.includes("file name");
  if (!hasFilename || (!hasSample && !vendorFormat)) {
    throw new Error("Required columns are missing. Include sample_name and expected_filename, or use the vendor MS format with Sample Type and File Name columns.");
  }
  const pairOccurrences = new Map<string, number>();
  const parsed = lines.slice(headerLine + 1).map((line, index) => {
    const values = parseDelimitedLine(line, delimiter).map((value) => value.trim());
    const value = (candidates: string[]) => {
      const normalizedCandidates = candidates.map(normalizeHeader);
      const headerIndex = headers.findIndex((header) => normalizedCandidates.includes(header));
      return headerIndex >= 0 ? values[headerIndex] ?? "" : "";
    };
    const sourceFilename = value(["expected_filename", "expected file", "filename", "file name", "file", "raw file", "raw_file"]);
    const hye = getHyeFilenameTags(sourceFilename, pairOccurrences);
    const suppliedSampleName = value(["sample_name", "sample", "sample id", "sample_id", "name"]);
    const sampleName = hye?.sampleName ?? (suppliedSampleName || sourceFilename);
    const expectedFilename = sourceFilename;
    const rowNumber = index + headerLine + 2;
    if (!sampleName) throw new Error(`Row ${rowNumber} is missing a sample name.`);
    if (!expectedFilename) throw new Error(`Row ${rowNumber} is missing a file name.`);
    const positionRaw = value(["position", "order", "injection", "index", "pos"]);
    const positionValue = Number(positionRaw);
    if (positionRaw && (!Number.isInteger(positionValue) || positionValue < 1) && !vendorFormat) {
      throw new Error(`Row ${rowNumber} has an invalid position.`);
    }
    const roleValue = value(["file_role", "role", "type"]).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    const vendorSampleType = value(["sample type"]).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    const normalizedRole = roleValue || (roleOptions.includes(vendorSampleType as WorklistImportRow["file_role"]) ? vendorSampleType : hye ? "hye" : "sample");
    if (roleValue && !roleOptions.includes(roleValue as WorklistImportRow["file_role"])) {
      throw new Error(`Row ${rowNumber} has unsupported file_role “${roleValue}”.`);
    }
    const fileRole = roleOptions.includes(normalizedRole as WorklistImportRow["file_role"])
      ? normalizedRole as WorklistImportRow["file_role"]
      : "sample";
    const qcProgramValue = value(["qc_program", "qc program", "qc", "program"]).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    const qcProgram: WorklistImportRow["qc_program"] = qcProgramValue === "hye" || fileRole === "hye" || hye
      ? "hye"
      : qcProgramValue === "prtc" || fileRole === "prtc" ? "prtc" : "";
    return {
      position: !vendorFormat && Number.isInteger(positionValue) && positionValue > 0 ? positionValue : index + 1,
      sample_name: sampleName,
      run_name: value(["run_name", "run", "injection_name"]) || sourceFilename,
      expected_filename: expectedFilename,
      file_role: fileRole,
      qc_program: qcProgram,
      condition: value(["condition", "group"]),
      well: value(["well", "vial", "autosampler_vial", "position"]),
      plate: value(["plate", "plate_id"]),
      hye_pair_label: value(["hye_pair_label", "hye pair", "qc_pair"]) || hye?.pairLabel || "",
      metadata: {
        ...Object.fromEntries(headers.map((header, headerIndex) => [header.replaceAll(" ", "_"), values[headerIndex] ?? ""])),
        source_format: vendorFormat ? `vendor_${instrumentKind}_worklist` : "csv_import",
        instrument_worklist_type: instrumentKind,
        source_filename: sourceFilename,
        role_tagging_required: vendorFormat && !hye && !roleOptions.includes(vendorSampleType as WorklistImportRow["file_role"]),
        role_confirmed: !vendorFormat || Boolean(hye) || roleOptions.includes(vendorSampleType as WorklistImportRow["file_role"]),
      },
    };
  });
  if (!parsed.length) throw new Error("No worklist injections were found.");
  const positions = parsed.map((row) => row.position);
  if (new Set(positions).size !== positions.length) throw new Error("Worklist positions must be unique.");
  const filenames = parsed.map((row) => row.expected_filename.toLowerCase());
  if (new Set(filenames).size !== filenames.length) throw new Error("Expected filenames must be unique.");
  validateHyePairs(parsed);
  return parsed;
}

export function validateWorklistTags(rows: WorklistImportRow[]) {
  for (const row of rows) {
    const metadata = row.metadata ?? {};
    if (metadata.role_tagging_required && metadata.role_confirmed !== true) {
      return `${row.expected_filename}: select the sample role in the worklist preview.`;
    }
    if (metadata.role_tagging_required && row.file_role === "sample") {
      const sampleType = String(metadata.sample_type ?? "").trim();
      if (!sampleType || sampleType.toLowerCase() === "unknown") {
        return `${row.expected_filename}: enter its sample type before importing.`;
      }
    }
    if ((row.file_role === "blank" || row.file_role === "true_blank") && !String(metadata.blank_type ?? "").trim()) {
      return `${row.expected_filename}: enter a blank type before importing.`;
    }
    if (row.file_role === "qc" && (!String(metadata.qc_stage ?? "").trim() || !String(metadata.qc_material ?? "").trim())) {
      return `${row.expected_filename}: enter a QC stage and material before importing.`;
    }
  }
  try {
    validateHyePairs(rows);
  } catch (error) {
    return error instanceof Error ? error.message : "HYE controls need a complete A/B pair.";
  }
  return "";
}

function validateHyePairs(rows: Array<Pick<WorklistImportRow, "sample_name" | "file_role" | "qc_program" | "hye_pair_label">>) {
  const pairs = new Map<string, string[]>();
  rows.filter((row) => row.file_role === "hye" || row.qc_program === "hye").forEach((row) => {
    const label = row.hye_pair_label?.trim() ?? "";
    if (!label) throw new Error(`${row.sample_name} needs an hye_pair_label.`);
    if (row.sample_name !== "HYE-A" && row.sample_name !== "HYE-B") throw new Error(`${label}: sample_name must be HYE-A or HYE-B.`);
    pairs.set(label, [...(pairs.get(label) ?? []), row.sample_name]);
  });
  for (const [label, mixes] of pairs) {
    if (mixes.length !== 2 || mixes.filter((mix) => mix === "HYE-A").length !== 1 || mixes.filter((mix) => mix === "HYE-B").length !== 1) {
      throw new Error(`${label} must contain exactly one HYE-A and one HYE-B injection.`);
    }
  }
}

function getHyeFilenameTags(filename: string, occurrences: Map<string, number>) {
  const match = /(?:^|[_\-\s])HYE[_\-\s]?([AB])(?:[_\-\s]|$)/i.exec(filename);
  if (!match) return null;
  const mix = match[1].toUpperCase();
  const stem = filename.replace(/\.[^.]+$/, "");
  let context = stem.replace(/(?:^|[_\-\s])HYE[_\-\s]?[AB](?=[_\-\s]|$)/i, "_HYE_");
  context = context.replace(/(?:^|[_-])B[A-Z]\d+/gi, "_").replace(/(?:^|[_-])Run\d+/gi, "_");
  const explicitReplicate = /(?:^|[_-])Rep(?:licate)?[_-]?(\d+)/i.exec(context);
  const baseContext = context.replace(/(?:^|[_-])Rep(?:licate)?[_-]?\d*/i, "_").replace(/[_-]+/g, "_").replace(/^_|_$/g, "");
  const occurrenceKey = `${baseContext}:${mix}`;
  const replicate = explicitReplicate?.[1] ?? String((occurrences.get(occurrenceKey) ?? 0) + 1);
  if (!explicitReplicate) occurrences.set(occurrenceKey, Number(replicate));
  const compactContext = baseContext.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 42);
  return { sampleName: `HYE-${mix}`, pairLabel: `HYE-${compactContext}-Rep${replicate}`.slice(0, 64) };
}

function parseDelimitedLine(line: string, delimiter: string) {
  const values: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === "\"" && quoted && next === "\"") {
      current += "\"";
      index += 1;
    } else if (char === "\"") {
      quoted = !quoted;
    } else if (char === delimiter && !quoted) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  if (quoted) throw new Error("The worklist contains an unterminated quoted field.");
  values.push(current);
  return values;
}
