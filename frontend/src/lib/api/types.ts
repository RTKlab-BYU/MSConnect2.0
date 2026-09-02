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

export type AnalysisPreset = {
  id: EntityId;
  code: string;
  name: string;
  analysis_type: string;
  description: string;
  defaults: Record<string, unknown>;
  required_metadata: string[];
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type FileMatchException = {
  id: EntityId;
  raw_file: EntityId;
  filename: string;
  project: EntityId | null;
  project_code?: string;
  experiment: EntityId | null;
  status: "open" | "resolved" | "ignored";
  reason: string;
  resolved_run: EntityId | null;
  resolved_run_name?: string;
  resolution_note: string;
  created_at: string;
  updated_at: string;
};

export type Experiment = {
  id: EntityId;
  project: EntityId;
  name: string;
  hypothesis: string;
  started_on: string | null;
  ended_on: string | null;
  created_by: EntityId | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type CurrentUser = {
  id: EntityId;
  username: string;
  email: string;
  is_superuser: boolean;
  global_role: "admin" | "pi" | "researcher" | "collaborator";
  email_verified_at: string | null;
  labs: Array<{
    id: EntityId;
    name: string;
    slug: string;
    role: "admin" | "pi" | "researcher" | "collaborator";
    facility_name: string;
    university_name: string;
  }>;
  active_lab_ids: EntityId[];
};

export type IntakeMetadata = {
  schema_version: string;
  institution: {
    name: string;
    department?: string;
  };
  contact: {
    name: string;
    email: string;
    phone?: string;
  };
  sample_planning: {
    organism: string;
    matrix: string;
    sample_count: number;
    plate_format: "96" | "384";
    plate_layout?: string;
  };
  shipping: {
    expectations?: string;
    handling_notes?: string;
  };
  billing: {
    invoice_email: string;
    po_reference?: string;
    billing_address?: Record<string, unknown>;
  };
  hazards: {
    handling_notes?: string;
  };
  notes?: string;
};

export type ProjectIntakeRequest = {
  id: EntityId;
  lab: EntityId;
  requested_title: string;
  requested_code: string;
  requested_pi: EntityId | null;
  objective: string;
  sample_count_estimate: number | null;
  acquisition_deadline: string | null;
  institution_name: string;
  contact_name: string;
  contact_email: string;
  invoice_email: string;
  organism: string;
  matrix: string;
  plate_format: string;
  shipping_notes: string;
  hazards_notes: string;
  metadata: IntakeMetadata;
  status: "submitted" | "in_review" | "approved" | "rejected";
  submitted_by: EntityId;
  reviewed_by: EntityId | null;
  review_note: string;
  reviewed_at: string | null;
  promoted_project: EntityId | null;
  created_at: string;
  updated_at: string;
};

export type IntakeMetrics = {
  totals: {
    requests: number;
    sample_count_estimate: number;
    approved: number;
    rejected: number;
    in_review: number;
    submitted: number;
  };
  by_institution: Array<{
    institution_name: string;
    count: number;
    sample_count_estimate: number;
    approved: number;
    rejected: number;
    in_review: number;
    submitted: number;
  }>;
  status_rows: Array<{
    institution_name: string;
    status: string;
    count: number;
    sample_volume: number | null;
  }>;
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
  fasta_path?: string;
  speclib_path?: string;
  fasta_upload_name?: string;
  speclib_upload_name?: string;
  diann_version: string;
  diann_settings: Record<string, unknown>;
};

export type PreAcquisitionSetupPreflightResponse = {
  title: string;
  code: string;
  source: "project_pipeline" | "site_defaults";
  source_label: string;
  source_detail: string;
  lab: { id: EntityId; name: string; facility: EntityId };
  instrument_configuration: InstrumentConfiguration | null;
  sample_count: number;
  healthy_count: number;
  diseased_count: number;
  hye_interval: number;
  planned_runs: number;
  processing_preset: string;
  diann_version: string;
  speclib_mode: string;
  reference_assets: Record<string, unknown>;
  settings: Record<string, unknown>;
  performance_tags: Record<string, unknown>;
  experimental_tags: Record<string, unknown>;
  options: string[];
  validation_errors: string[];
  is_valid: boolean;
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

export type ProjectQuickStartPayload = {
  title: string;
  code?: string;
};

export type ProjectQuickStartResponse = {
  project: Project;
  experiment: {
    id: EntityId;
    name: string;
  };
};

export type WorklistImportRow = {
  position: number;
  run_name?: string;
  sample_name: string;
  expected_filename: string;
  file_role: RawFile["file_role"];
  qc_program?: "" | "hye" | "prtc";
  status?: Run["status"];
  well?: string;
  plate?: string;
  condition?: string;
  hye_pair_label?: string;
  notes?: string;
  metadata?: Record<string, unknown>;
};

export type WorklistImportPayload = {
  worklist_name: string;
  experiment_name?: string;
  rows: WorklistImportRow[];
};

export type WorklistImportResponse = {
  worklist: AcquisitionWorklist;
  samples_imported: number;
  runs_imported: number;
  worklist_entries_imported: number;
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
  experiment_id?: EntityId;
  experiment_name?: string;
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
  file_role: "sample" | "qc" | "hye" | "prtc" | "library" | "blank" | "true_blank" | "wash" | "calibration";
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
  intended_filename: string;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  chunk_size_bytes: number;
  chunk_count: number;
  checksum_sha256: string;
  status: "created" | "uploading" | "complete" | "failed";
  file_role: RawFile["file_role"];
  completed_raw_file: EntityId | null;
  match_metadata: Record<string, unknown>;
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
  required_engine: string;
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
  ip_address: string;
  health: "green" | "yellow" | "red";
  active_control: Record<string, unknown>;
  seconds_since_heartbeat: number | null;
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

export type DeploymentSettings = {
  scope: string;
  prtc_skyline_pipeline: EntityId | null;
  prtc_skyline_pipeline_name: string;
  prtc_skyline_pipeline_version: string;
  targeted_skyline_pipeline: EntityId | null;
  targeted_skyline_pipeline_name: string;
  targeted_skyline_pipeline_version: string;
  metadata: Record<string, unknown>;
  updated_at: string;
};

export type DiannPreflightResponse = {
  project: Project;
  source: "project_pipeline" | "site_defaults";
  source_label: string;
  source_detail: string;
  worklist: AcquisitionWorklist | null;
  pipeline: ProcessingPipeline | null;
  processing_preset: string;
  diann_version: string;
  speclib_mode: string;
  reference_assets: Record<string, unknown>;
  settings: Record<string, unknown>;
  performance_tags: Record<string, unknown>;
  experimental_tags: Record<string, unknown>;
  options: string[];
  validation_errors: string[];
  is_valid: boolean;
};

export type PipelineEvent = {
  id: EntityId;
  project: EntityId | null;
  project_code?: string;
  experiment: EntityId | null;
  experiment_name?: string;
  event_type: string;
  from_status: string;
  to_status: string;
  actor: EntityId | null;
  actor_username?: string;
  message: string;
  payload: Record<string, unknown>;
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
  stale: number;
};

export type SystemHealthSnapshot = {
  status: "green" | "yellow" | "red";
  server_time: string;
  readiness: {
    healthz: {
      ok: boolean;
      status: "green" | "yellow" | "red";
      label: string;
      detail: string;
    };
    database: {
      ok: boolean;
      path?: string;
      error?: string;
    };
    incoming_raw_root: {
      ok: boolean;
      path?: string;
      error?: string;
    };
    raw_file_storage_root: {
      ok: boolean;
      path?: string;
      error?: string;
    };
    results_root: {
      ok: boolean;
      path?: string;
      error?: string;
    };
    media_root: {
      ok: boolean;
      path?: string;
      error?: string;
    };
    readyz: {
      ok: boolean;
      status: "green" | "yellow" | "red";
      label: string;
      detail: string;
    };
  };
  nodes: {
    total: number;
    connected: number;
    stale: number;
    offline: number;
    watcher: {
      node_type: string;
      total: number;
      connected: number;
      stale: number;
      offline: number;
      latest_heartbeat_at: string | null;
    };
    processor: {
      node_type: string;
      total: number;
      connected: number;
      stale: number;
      offline: number;
      latest_heartbeat_at: string | null;
    };
    by_type: Array<{
      node_type: string;
      total: number;
      connected: number;
      stale: number;
      offline: number;
      latest_heartbeat_at: string | null;
    }>;
  };
  jobs: {
    active: number;
    failed: number;
  };
  raw_files: {
    total: number;
    unmatched: number;
  };
  alerts: Array<{
    severity: "critical" | "warning" | "info";
    code: string;
    title: string;
    detail: string;
    route?: string;
  }>;
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
  qc_program: "" | "hye" | "prtc";
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

export type ProjectResearcherRun = {
  run: Run;
  sample: Sample;
  worklist_entry_id: EntityId | null;
  worklist_name: string;
  raw_file: RawFile | null;
  raw_file_count: number;
  processing_job: ProcessingJob | null;
  processing_job_count: number;
  stats: {
    protein_quant_count: number;
    peptide_quant_count: number;
    reported_protein_count: number;
    reported_peptide_count: number;
    reported_precursor_count: number;
    ms1_feature_count: number;
    ms2_spectra_count: number;
    indexed_spectra_count: number;
    indexed_ms1_spectra_count: number;
    indexed_ms2_spectra_count: number;
  };
};

export type ProjectResearcherStatus = {
  project: Project;
  summary: ProjectSummary;
  experiment?: Experiment;
  system_health: {
    status: "green" | "yellow" | "red";
    failed_jobs: number;
    active_jobs: number;
    missing_raw_files: number;
  };
  runs: ProjectResearcherRun[];
};

export type FindingsWorkspace = {
  id: EntityId;
  project: EntityId;
  project_code: string;
  project_title: string;
  mode: "personal" | "shared";
  data_strategy: "manifest" | "symlink";
  root_path: string;
  workspace_path: string;
  status: "prepared" | "active" | "indexed" | "error";
  plugin_marketplace: string;
  plugin_name: string;
  plugin_version: string;
  findings_count: number;
  reports_count: number;
  latest_report_path: string;
  last_indexed_at: string | null;
  error_message: string;
  metadata: Record<string, unknown>;
  walkthrough_path: string;
  claude_commands: string[];
  created_at: string;
  updated_at: string;
};

export type FindingsWorkspaceResponse = {
  workspace: FindingsWorkspace | null;
  default_root_path?: string;
  claude_commands?: string[];
};

export type PrepareFindingsWorkspacePayload = {
  root_path?: string;
  mode: "personal" | "shared";
  data_strategy: "manifest" | "symlink";
};

export type PrepareFindingsWorkspaceResponse = {
  workspace: FindingsWorkspace;
  created_paths: string[];
  kept_paths: string[];
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
    status: "pass" | "warn" | "warning" | "fail" | "failed" | "incomplete" | "unknown";
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
  machine_key: string;
  machine_label: string;
  a_machine_key: string;
  a_machine_label: string;
  b_machine_key: string;
  b_machine_label: string;
  status: "pass" | "warning" | "failed" | "incomplete";
  shared_total_n: number;
  completed_at: string | null;
  a_run_id: EntityId | null;
  b_run_id: EntityId | null;
  a_run_name: string;
  b_run_name: string;
  a_filename: string;
  b_filename: string;
  score: number | null;
  worst_relative_error: number | null;
  health_score: number | null;
  health_status: "pass" | "warning" | "failed" | "incomplete";
  organisms: QcPairOrganism[];
};

export type QcMachineSummary = {
  machine_key: string;
  machine_label: string;
  pair_count: number;
  complete_pair_count: number;
  mean_score: number | null;
  stddev_score: number | null;
  lower_band: number | null;
  upper_band: number | null;
  latest_completed_at: string | null;
};

export type QcMachineSeriesPoint = {
  machine_key: string;
  machine_label: string;
  project_id: EntityId;
  project_code: string;
  worklist_id: EntityId;
  worklist_name: string;
  pair_label: string;
  completed_at: string | null;
  score: number | null;
  health_score: number | null;
  health_status: string;
  mean_score: number | null;
  lower_band: number | null;
  upper_band: number | null;
  status: string;
  pair_count: number;
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
  runs?: QcPrtcRun[];
  machine_summaries?: QcMachineSummary[];
  machine_series?: QcMachineSeriesPoint[];
};

export type QcPrtcRun = {
  job_id: EntityId;
  run_id: EntityId;
  run_name: string;
  filename: string;
  status: "pass" | "warn" | "warning" | "fail" | "failed" | "incomplete" | "unknown";
  expected_peptide_count: number;
  detected_peptide_count: number;
  missing_peptide_count: number;
  out_of_tolerance_peptide_count: number;
  total_area: number | null;
  mean_rt_shift_seconds: number | null;
  max_abs_rt_shift_seconds: number | null;
  missing_peptides: string[];
  out_of_tolerance_peptides: string[];
  finished_at: string | null;
  machine_key?: string;
  machine_label?: string;
  project_id?: EntityId;
  project_code?: string;
};
