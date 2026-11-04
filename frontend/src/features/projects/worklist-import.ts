import type { WorklistImportRow } from "@/lib/api/types";

export const roleOptions = ["sample", "qc", "hye", "prtc", "library", "blank", "true_blank", "wash", "calibration"] as const;

export type InstrumentWorklistKind = "lc" | "ms";

export type WorklistAnnotation = {
  expected_filename: string;
  sample_name: string;
  file_role: WorklistImportRow["file_role"];
  qc_program?: WorklistImportRow["qc_program"];
  hye_pair_label?: string;
  condition?: string;
  notes?: string;
  metadata: Record<string, unknown>;
};

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

export function parseWorklistAnnotationText(text: string): WorklistAnnotation[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) throw new Error("The annotation file needs a header and at least one tagged injection.");
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const normalizeHeader = (header: string) => header.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const headers = parseDelimitedLine(lines[0], delimiter).map(normalizeHeader);
  const requiredHeaders = ["expected_filename", "sample_name", "file_role"];
  const missingHeaders = requiredHeaders.filter((header) => !headers.includes(header));
  if (missingHeaders.length) throw new Error(`Annotation file is missing required columns: ${missingHeaders.join(", ")}.`);

  const metadataHeaders = [
    "sample_type",
    "blank_type",
    "qc_stage",
    "qc_material",
    "prep_batch",
    "replicate",
    "subject_id",
    "matrix",
    "species",
    "digestion_protocol",
    "enrichment_protocol",
  ];
  const rows = lines.slice(1).map((line, index) => {
    const values = parseDelimitedLine(line, delimiter).map((value) => value.trim());
    const value = (header: string) => {
      const column = headers.indexOf(header);
      return column >= 0 ? values[column] ?? "" : "";
    };
    const rowNumber = index + 2;
    const expectedFilename = value("expected_filename");
    const sampleName = value("sample_name");
    if (!expectedFilename) throw new Error(`Annotation row ${rowNumber} is missing expected_filename.`);
    if (!sampleName) throw new Error(`Annotation row ${rowNumber} is missing sample_name.`);
    const role = value("file_role").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    if (!roleOptions.includes(role as WorklistImportRow["file_role"])) {
      throw new Error(`Annotation row ${rowNumber} has unsupported file_role “${role}”.`);
    }
    const fileRole = role as WorklistImportRow["file_role"];
    const qcProgramValue = value("qc_program").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    if (qcProgramValue && qcProgramValue !== "hye" && qcProgramValue !== "prtc") {
      throw new Error(`Annotation row ${rowNumber} has unsupported qc_program “${qcProgramValue}”.`);
    }
    const qcProgram = (qcProgramValue || (fileRole === "hye" ? "hye" : fileRole === "prtc" ? "prtc" : "")) as WorklistImportRow["qc_program"];
    if ((qcProgram === "hye" && fileRole !== "hye") || (qcProgram === "prtc" && fileRole !== "prtc")) {
      throw new Error(`Annotation row ${rowNumber}: HYE and PRTC programs must use their matching file_role.`);
    }

    const metadata = Object.fromEntries(metadataHeaders.map((header) => [header, value(header)]).filter(([, item]) => item));
    if ((fileRole === "blank" || fileRole === "true_blank") && !metadata.blank_type) {
      throw new Error(`Annotation row ${rowNumber}: blank_type is required for blank injections.`);
    }
    if (fileRole === "qc" && (!metadata.qc_stage || !metadata.qc_material)) {
      throw new Error(`Annotation row ${rowNumber}: qc_stage and qc_material are required for QC injections.`);
    }
    return {
      expected_filename: expectedFilename,
      sample_name: sampleName,
      file_role: fileRole,
      qc_program: qcProgram,
      hye_pair_label: value("hye_pair_label"),
      condition: value("condition"),
      notes: value("notes"),
      metadata,
    } satisfies WorklistAnnotation;
  });

  const keys = rows.map((row) => normalizeFilenameKey(row.expected_filename));
  if (new Set(keys).size !== keys.length) throw new Error("Annotation filenames must be unique.");
  validateHyePairs(rows);
  return rows;
}

export function applyWorklistAnnotations(
  rows: WorklistImportRow[],
  annotations: WorklistAnnotation[] | null,
  options: { requireFullMatch?: boolean } = {},
): WorklistImportRow[] {
  const requireFullMatch = options.requireFullMatch ?? true;
  if (!annotations) {
    const issue = rows.map(vendorAnnotationIssue).find(Boolean);
    if (issue) throw new Error(issue);
    return rows;
  }

  const annotationsByFilename = new Map(annotations.map((annotation) => [normalizeFilenameKey(annotation.expected_filename), annotation]));
  const rowKeys = new Set(rows.map((row) => normalizeFilenameKey(row.expected_filename)));
  const extra = annotations.find((annotation) => !rowKeys.has(normalizeFilenameKey(annotation.expected_filename)));
  if (extra && requireFullMatch) throw new Error(`Annotation filename “${extra.expected_filename}” was not found in the MS worklist.`);

  const annotatedKeys = new Set<string>();
  const annotatedRows = rows.map((row) => {
    const key = normalizeFilenameKey(row.expected_filename);
    const annotation = annotationsByFilename.get(key);
    if (!annotation) {
      if (requireFullMatch) throw new Error(`${row.expected_filename} has no annotation. Add one row for every MS injection.`);
      return row;
    }
    annotatedKeys.add(key);
    return {
      ...row,
      sample_name: annotation.sample_name,
      file_role: annotation.file_role,
      qc_program: annotation.qc_program ?? "",
      hye_pair_label: annotation.hye_pair_label ?? "",
      condition: annotation.condition ?? "",
      notes: annotation.notes ?? "",
      metadata: {
        ...row.metadata,
        vendor_sample_type: row.metadata?.sample_type ?? "",
        ...annotation.metadata,
        annotation_source: "worklist_annotation_csv",
      },
    };
  });
  if (requireFullMatch && annotations.some((annotation) => !annotatedKeys.has(normalizeFilenameKey(annotation.expected_filename)))) {
    throw new Error("The annotation CSV contains rows that do not match an MS injection.");
  }
  if (requireFullMatch) validateHyePairs(annotatedRows);
  return annotatedRows;
}

function vendorAnnotationIssue(row: WorklistImportRow) {
  const sourceFormat = String(row.metadata?.source_format ?? "");
  if (!sourceFormat.startsWith("vendor_")) return "";
  const vendorType = String(row.metadata?.sample_type ?? "").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (row.file_role === "sample" && !roleOptions.includes(vendorType as WorklistImportRow["file_role"])) {
    return `${row.expected_filename} has an unknown vendor sample type. Upload the annotation CSV and assign its role before importing.`;
  }
  if ((row.file_role === "blank" || row.file_role === "true_blank") && !row.metadata?.blank_type) {
    return `${row.expected_filename} is a vendor blank and needs a blank_type in the annotation CSV.`;
  }
  if (row.file_role === "qc" && (!row.metadata?.qc_stage || !row.metadata?.qc_material)) {
    return `${row.expected_filename} is a vendor QC and needs qc_stage and qc_material in the annotation CSV.`;
  }
  return "";
}

function normalizeFilenameKey(filename: string) {
  return filename.trim().toLocaleLowerCase();
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
