export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type ListResponse<T> = T[] | Paginated<T>;

export type EntityId = number;

export type Project = {
  id: EntityId;
  lab: EntityId;
  title: string;
  code: string;
  pi: EntityId;
  status: "active" | "paused" | "complete" | "archived";
  description: string;
  created_at: string;
  updated_at: string;
};

export type PreAcquisitionSetupPayload = {
  title: string;
  code: string;
  sample_count?: number;
  healthy_count?: number;
  diseased_count?: number;
  sample_rows?: Array<Record<string, unknown>>;
  plate_type: "96" | "384";
  hye_interval: number;
  experiment_name: string;
  worklist_name: string;
  instrument_configuration?: EntityId | null;
  organisms: string[];
  processing_preset: string;
  fasta_upload_name?: string;
  speclib_upload_name?: string;
  diann_version: string;
  diann_settings: Record<string, unknown>;
};

export type PreAcquisitionSetupResponse = {
  project: Project;
  experiment: {
    id: EntityId;
    name: string;
  };
  worklist: AcquisitionWorklist;
  pipeline: ProcessingPipeline;
  samples_created: number;
  runs_created: number;
  worklist_entries_created: number;
  expected_filenames: string[];
};

export type InstrumentConfiguration = {
  id: EntityId;
  facility: EntityId;
  name: string;
  lc_instrument: EntityId | null;
  ms_instrument: EntityId | null;
  method_name: string;
  column_description: string;
  gradient_description: string;
  ion_source: string;
  active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProjectSummary = {
  project_id: EntityId;
  project_code: string;
  experiment_count: number;
  sample_count: number;
  run_count: number;
  acquisition_worklist_count: number;
  raw_file_count: number;
  processing_job_count: number;
  missing_raw_file_count: number;
  protein_quant_count: number;
  protein_identification_count: number;
  peptide_quant_count: number;
  peptide_identification_count: number;
  reported_protein_count: number;
  reported_peptide_count: number;
  reported_precursor_count: number;
  ms1_feature_count: number;
  ms2_spectra_count: number;
  indexed_spectra_count: number;
  indexed_ms1_spectra_count: number;
  indexed_ms2_spectra_count: number;
  artifact_count: number;
  derivative_count: number;
  raw_files_by_status: CountBy<"status">;
  raw_files_by_role: CountBy<"file_role">;
  jobs_by_status: CountBy<"status">;
  worklists_by_status: CountBy<"status">;
};

export type CountBy<TKey extends string> = Array<Record<TKey, string> & { count: number }>;

export type RawFile = {
  id: EntityId;
  run: EntityId | null;
  source_path: string;
  storage_path: string;
  filename: string;
  checksum_sha256: string;
  size_bytes: number;
  acquired_at: string | null;
  imported_at: string | null;
  status: "discovered" | "validated" | "imported" | "processed" | "failed";
  file_role: "sample" | "qc" | "library" | "blank" | "wash" | "calibration";
  match_confidence: number | null;
  failure_reason: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type RawFileDerivative = {
  id: EntityId;
  raw_file: EntityId;
  raw_file_filename: string;
  project_id: EntityId;
  project_code: string;
  derivative_type: "mzml" | "mzmlb" | "mgf" | "spectrum_index" | "preview_json" | "vendor_metadata";
  status: "queued" | "running" | "ready" | "failed";
  path: string;
  format: string;
  size_bytes: number | null;
  checksum_sha256: string;
  created_by_job: EntityId | null;
  error_message: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SpectrumSummary = {
  id: string;
  index: number | null;
  scan_number: number | null;
  ms_level: number | null;
  retention_time_seconds: number | null;
  base_peak_mz: number | null;
  base_peak_intensity: number | null;
  tic: number | null;
  precursor_mz: number | null;
};

export type SpectraResponse = {
  raw_file: RawFile;
  index_derivative: RawFileDerivative | null;
  count: number;
  spectra: SpectrumSummary[];
};

export type SpectrumDetailResponse = {
  raw_file: RawFile;
  index_derivative: RawFileDerivative | null;
  spectrum: SpectrumSummary & { peaks?: Array<[number, number]> };
};

export type ChromatogramsResponse = {
  raw_file: RawFile;
  index_derivative: RawFileDerivative | null;
  chromatograms: {
    tic?: Array<[number, number]>;
    bpc?: Array<[number, number]>;
  };
};

export type DirectUploadPart = {
  part_number: number;
  start: number;
  end: number;
  method: "PUT";
  url: string;
  headers: Record<string, string>;
};

export type DirectUploadSession = {
  id: EntityId;
  project: EntityId;
  run: EntityId | null;
  upload_id: string;
  filename: string;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  chunk_size_bytes: number;
  chunk_count: number;
  checksum_sha256: string;
  status: "created" | "uploading" | "complete" | "failed";
  file_role: RawFile["file_role"];
  completed_raw_file: EntityId | null;
  metadata: Record<string, unknown>;
  upload_urls: DirectUploadPart[];
  created_at: string;
  updated_at: string;
};

export type ProcessingJob = {
  id: EntityId;
  run: EntityId;
  pipeline: EntityId;
  raw_file: EntityId;
  node: EntityId | null;
  node_name: string | null;
  project_id: EntityId;
  project_code: string;
  run_name: string;
  raw_file_filename: string;
  pipeline_name: string;
  pipeline_version: string;
  status: "queued" | "assigned" | "running" | "complete" | "failed" | "retrying";
  started_at: string | null;
  finished_at: string | null;
  log_path: string;
  error_message: string;
  stats: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProcessingJobArtifact = {
  id: EntityId;
  job: EntityId;
  job_status: ProcessingJob["status"];
  raw_file_filename: string;
  run_name: string;
  project_id: EntityId;
  project_code: string;
  artifact_type:
    | "log"
    | "protein_table"
    | "peptide_table"
    | "diann_report"
    | "fragpipe_output"
    | "enterprise_export"
    | "matrix"
    | "raw_output"
    | "other";
  path: string;
  format: string;
  size_bytes: number | null;
  checksum_sha256: string;
  retained: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProcessingNode = {
  id: EntityId;
  name: string;
  node_type: string;
  status: "offline" | "idle" | "busy" | "error";
  container_image: string;
  endpoint_url: string;
  last_heartbeat_at: string | null;
  settings: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProcessingPipeline = {
  id: EntityId;
  name: string;
  version: string;
  container_image: string;
  parameters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProcessingJobOverview = {
  total: number;
  active: number;
  failed: number;
  by_status: CountBy<"status">;
  by_pipeline: Array<{
    pipeline_id: EntityId;
    pipeline__name: string;
    pipeline__version: string;
    count: number;
  }>;
  by_node: Array<{
    node_id: EntityId | null;
    node__name: string | null;
    count: number;
  }>;
};

export type ProcessingNodeOverview = {
  total: number;
  by_status: CountBy<"status">;
  by_type: CountBy<"node_type">;
};

export type RawFileOverview = {
  total: number;
  by_status: CountBy<"status">;
  by_role: CountBy<"file_role">;
  unmatched: number;
};

export type Sample = {
  id: EntityId;
  experiment: EntityId;
  name: string;
  external_id: string;
  species: string;
  matrix: string;
  digestion_protocol: string;
  enrichment_protocol: string;
  submitted_by: EntityId | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: EntityId;
  sample: EntityId;
  configuration: EntityId | null;
  run_name: string;
  acquired_by: EntityId | null;
  acquisition_started_at: string | null;
  acquisition_ended_at: string | null;
  status: "planned" | "acquired" | "imported" | "processed" | "failed";
  file_role: RawFile["file_role"];
  expected_filename: string;
  worklist_position: number | null;
  hye_pair_label: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type RunSummary = {
  run: Run;
  sample: Sample;
  raw_files: RawFile[];
  processing_jobs: ProcessingJob[];
  derivatives: RawFileDerivative[];
  artifacts: ProcessingJobArtifact[];
  stats: {
    raw_file_count: number;
    processing_job_count: number;
    protein_quant_count: number;
    protein_identification_count: number;
    peptide_quant_count: number;
    peptide_identification_count: number;
    reported_protein_count: number;
    reported_peptide_count: number;
    reported_precursor_count: number;
    ms1_feature_count: number;
    ms2_spectra_count: number;
    indexed_spectra_count: number;
    indexed_ms1_spectra_count: number;
    indexed_ms2_spectra_count: number;
    artifact_count: number;
    derivative_count: number;
  };
};

export type AcquisitionWorklist = {
  id: EntityId;
  experiment: EntityId;
  name: string;
  configuration: EntityId | null;
  status: "draft" | "ready" | "acquiring" | "complete";
  generated_by: EntityId | null;
  notes: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type QcOverview = {
  program: "hye" | "prtc";
  configured: boolean;
  qc_injection_count: number;
  complete_pair_count: number;
  out_of_spec_pair_count: number;
  missing_raw_file_count: number;
  latest_completed_at: string | null;
  pair_status_counts: Array<{
    status: "pass" | "warning" | "failed" | "incomplete";
    count: number;
  }>;
  empty_message: string;
};

export type QcPairOrganism = {
  organism: string;
  shared_n: number;
  median_log2_a: number | null;
  median_log2_b: number | null;
  observed_ratio: number | null;
  ideal_a: number;
  ideal_b: number;
  ideal_ratio: number;
  relative_error: number | null;
  status: "pass" | "warning" | "failed" | "incomplete";
};

export type QcPair = {
  project_id: EntityId;
  project_code: string;
  worklist_id: EntityId;
  worklist_name: string;
  pair_label: string;
  status: "pass" | "warning" | "failed" | "incomplete";
  shared_total_n: number;
  completed_at: string | null;
  a_run_id: EntityId | null;
  b_run_id: EntityId | null;
  a_run_name: string;
  b_run_name: string;
  a_filename: string;
  b_filename: string;
  organisms: QcPairOrganism[];
};

export type QcDetails = {
  program: "hye" | "prtc";
  configured: boolean;
  thresholds: {
    pass_relative_error: number;
    warning_relative_error: number;
  };
  empty_message: string;
  pairs: QcPair[];
};
