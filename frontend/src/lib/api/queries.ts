import { getResource, paginatedResource, patchResource, postResource, type ListParams } from "@/lib/api/client";
import type {
  AcquisitionWorklist,
  AnalysisPreset,
  ChromatogramsResponse,
  CurrentUser,
  DeploymentSettings,
  DeploymentRelease,
  DiannPreflightResponse,
  Experiment,
  FindingsWorkspaceResponse,
  DirectUploadSession,
  FileMatchException,
  InstrumentConfiguration,
  Paginated,
  PipelineEvent,
  IntakeMetrics,
  IntakeMetadata,
  ProjectIntakeRequest,
  PrepareFindingsWorkspacePayload,
  PrepareFindingsWorkspaceResponse,
  PreAcquisitionSetupPayload,
  PreAcquisitionSetupPreflightResponse,
  PreAcquisitionSetupResponse,
  ProcessingJob,
  ProcessingJobOverview,
  ProcessingNode,
  ProcessingNodeOverview,
  ProcessingPipeline,
  Project,
  ProjectQuickStartPayload,
  ProjectQuickStartResponse,
  ProjectResearcherStatus,
  ProjectSummary,
  QcDetails,
  QcOverview,
  RawFile,
  RawFileDerivative,
  RawFileOverview,
  Run,
  RunSummary,
  Sample,
  SystemHealthSnapshot,
  SpectraResponse,
  SpectrumDetailResponse,
  WorklistImportPayload,
  WorklistImportResponse,
} from "@/lib/api/types";

export const queryKeys = {
  projects: (params?: ListParams) => ["projects", params] as const,
  project: (id: number) => ["project", id] as const,
  projectExperiments: (id: number) => ["project", id, "experiments"] as const,
  experiment: (id: number) => ["experiment", id] as const,
  directUploadSessions: (params?: ListParams) => ["direct-upload-sessions", params] as const,
  projectSummary: (id: number) => ["project", id, "summary"] as const,
  projectResearcherStatus: (id: number, params?: ListParams) => ["project", id, "researcher-status", params] as const,
  projectDiannPreflight: (id: number, params?: ListParams) => ["project", id, "diann-preflight", params] as const,
  analysisPresets: (params?: ListParams) => ["analysis-presets", params] as const,
  fileMatchExceptions: (params?: ListParams) => ["file-match-exceptions", params] as const,
  pipelineEvents: (params?: ListParams) => ["pipeline-events", params] as const,
  projectProcessingJobs: (id: number) => ["project", id, "processing-jobs"] as const,
  findingsWorkspace: (id: number) => ["project", id, "findings-workspace"] as const,
  currentUser: () => ["current-user"] as const,
  rawFiles: (params: ListParams) => ["raw-files", params] as const,
  rawFilesOverview: (params?: ListParams) => ["raw-files", "overview", params] as const,
  rawFileDerivatives: (params?: ListParams) => ["raw-file-derivatives", params] as const,
  rawFileSpectra: (id: number, params?: ListParams) => ["raw-files", id, "spectra", params] as const,
  rawFileSpectrum: (id: number, spectrumId: string) => ["raw-files", id, "spectra", spectrumId] as const,
  rawFileChromatograms: (id: number) => ["raw-files", id, "chromatograms"] as const,
  processingJobs: (params: ListParams) => ["processing-jobs", params] as const,
  processingJobsOverview: (params?: ListParams) => ["processing-jobs", "overview", params] as const,
  processingNodes: (params?: ListParams) => ["processing-nodes", params] as const,
  processingNodesOverview: (params?: ListParams) => ["processing-nodes", "overview", params] as const,
  processingPipelines: (params?: ListParams) => ["processing-pipelines", params] as const,
  deploymentSettings: () => ["deployment-settings"] as const,
  deploymentReleases: (params?: ListParams) => ["deployment-releases", params] as const,
  instrumentConfigurations: (params?: ListParams) => ["instrument-configurations", params] as const,
  systemHealth: () => ["system-health"] as const,
  samples: (params: ListParams) => ["samples", params] as const,
  runs: (params: ListParams) => ["runs", params] as const,
  runSummary: (id: number) => ["runs", id, "summary"] as const,
  acquisitions: (params: ListParams) => ["acquisition-worklists", params] as const,
  qcOverview: (params?: ListParams) => ["qc", "overview", params] as const,
  qcDetails: (params?: ListParams) => ["qc", "details", params] as const,
  intakeRequests: (params?: ListParams) => ["intake-requests", params] as const,
  intakeMetrics: () => ["intake-requests", "metrics"] as const,
};

export function fetchCurrentUser(): Promise<CurrentUser> {
  return getResource<CurrentUser>("/auth/me/");
}

export function signupAccount(payload: {
  username: string;
  email: string;
  password: string;
  lab_name?: string;
  institution_name?: string;
  membership_role?: "collaborator" | "pi";
}): Promise<{ user: CurrentUser; verification: { token: string; verify_url: string }; lab_id: number; lab_code: string }> {
  return postResource("/auth/signup/", payload);
}

export function fetchProjects(params?: ListParams): Promise<Paginated<Project>> {
  return paginatedResource<Project>("/projects/", { ordering: "-updated_at", ...params });
}

export function fetchAnalysisPresets(params?: ListParams): Promise<Paginated<AnalysisPreset>> {
  return paginatedResource<AnalysisPreset>("/analysis-presets/", { active: true, ordering: "name", ...params });
}

export function fetchFileMatchExceptions(params?: ListParams): Promise<Paginated<FileMatchException>> {
  return paginatedResource<FileMatchException>("/file-match-exceptions/", { ordering: "status,created_at", ...params });
}

export function resolveFileMatchException(id: number, run: number, resolution_note = "") {
  return postResource<FileMatchException>(`/file-match-exceptions/${id}/resolve/`, { run, resolution_note });
}

export function fetchProject(id: number): Promise<Project> {
  return getResource<Project>(`/projects/${id}/`);
}

export function fetchExperiments(params?: ListParams): Promise<Paginated<Experiment>> {
  return paginatedResource<Experiment>("/experiments/", { ordering: "-updated_at", ...params });
}

export function fetchExperiment(id: number): Promise<Experiment> {
  return getResource<Experiment>(`/experiments/${id}/`);
}

export function fetchDirectUploadSessions(params?: ListParams): Promise<Paginated<DirectUploadSession>> {
  return paginatedResource<DirectUploadSession>("/direct-uploads/", { ordering: "-updated_at", ...params });
}

export function fetchProjectSummary(id: number): Promise<ProjectSummary> {
  return getResource<ProjectSummary>(`/projects/${id}/summary/`);
}

export function fetchProjectResearcherStatus(id: number, params?: ListParams): Promise<ProjectResearcherStatus> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<ProjectResearcherStatus>(`/projects/${id}/researcher-status/${query.toString() ? `?${query}` : ""}`);
}

export function fetchProjectDiannPreflight(id: number, params?: ListParams): Promise<DiannPreflightResponse> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<DiannPreflightResponse>(`/projects/${id}/diann-preflight/${query.toString() ? `?${query}` : ""}`);
}

export function updateProjectDiannSettings(id: number, experiment: number, settings: Record<string, unknown>) {
  return patchResource<DiannPreflightResponse>(`/projects/${id}/diann-settings/?experiment=${experiment}`, { settings });
}

export function fetchPipelineEvents(params?: ListParams): Promise<Paginated<PipelineEvent>> {
  return paginatedResource<PipelineEvent>("/pipeline-events/", { ordering: "-created_at", ...params });
}

export function fetchIntakeRequests(params?: ListParams): Promise<Paginated<ProjectIntakeRequest>> {
  return paginatedResource<ProjectIntakeRequest>("/intake-requests/", { ordering: "-updated_at", ...params });
}

export function fetchIntakeRequest(id: number): Promise<ProjectIntakeRequest> {
  return getResource<ProjectIntakeRequest>(`/intake-requests/${id}/`);
}

export type IntakeRequestCreatePayload = {
  lab: number;
  requested_title: string;
  requested_code: string;
  objective: string;
  sample_count_estimate: number;
  acquisition_deadline: string | null;
  institution_name: string;
  contact_name: string;
  contact_email: string;
  invoice_email: string;
  organism: string;
  matrix: string;
  plate_format: "96" | "384";
  shipping_notes: string;
  hazards_notes: string;
  metadata: IntakeMetadata;
};

export function createIntakeRequest(payload: IntakeRequestCreatePayload) {
  return postResource<ProjectIntakeRequest>("/intake-requests/", payload);
}

export function reviewIntakeRequest(id: number, payload: { status: ProjectIntakeRequest["status"]; review_note?: string }) {
  return postResource<ProjectIntakeRequest>(`/intake-requests/${id}/review/`, payload);
}

export function promoteIntakeRequest(id: number) {
  return postResource<{ intake_request: ProjectIntakeRequest; project_id: number; project_code: string }>(`/intake-requests/${id}/promote/`, {});
}

export function fetchIntakeMetrics() {
  return getResource<IntakeMetrics>("/intake-requests/metrics/");
}

export function fetchFindingsWorkspace(projectId: number): Promise<FindingsWorkspaceResponse> {
  return getResource<FindingsWorkspaceResponse>(`/capabilities/findings-workflow/projects/${projectId}/workspace/`);
}

export function prepareFindingsWorkspace(projectId: number, payload: PrepareFindingsWorkspacePayload): Promise<PrepareFindingsWorkspaceResponse> {
  return postResource<PrepareFindingsWorkspaceResponse>(`/capabilities/findings-workflow/projects/${projectId}/workspace/`, payload);
}

export function indexFindingsWorkspace(workspaceId: number): Promise<FindingsWorkspaceResponse> {
  return postResource<FindingsWorkspaceResponse>(`/capabilities/findings-workflow/workspaces/${workspaceId}/index/`, {});
}

export function quickStartProject(payload: ProjectQuickStartPayload): Promise<ProjectQuickStartResponse> {
  return postResource<ProjectQuickStartResponse>("/projects/quick-start/", payload);
}

export function createPreAcquisitionSetup(payload: PreAcquisitionSetupPayload): Promise<PreAcquisitionSetupResponse> {
  return postResource<PreAcquisitionSetupResponse>("/projects/pre-acquisition-setup/", payload);
}

export function previewPreAcquisitionSetup(payload: PreAcquisitionSetupPayload): Promise<PreAcquisitionSetupPreflightResponse> {
  return postResource<PreAcquisitionSetupPreflightResponse>("/projects/pre-acquisition-preflight/", payload);
}

export function importProjectWorklist(projectId: number, payload: WorklistImportPayload): Promise<WorklistImportResponse> {
  return postResource<WorklistImportResponse>(`/projects/${projectId}/import-worklist/`, payload);
}

export function queueProjectReadyRuns(projectId: number, experimentId?: number): Promise<{ queued: number; jobs: ProcessingJob[] }> {
  return postResource(`/projects/${projectId}/queue-ready-runs/`, experimentId ? { experiment: experimentId } : {});
}

export function queueProjectRuns(projectId: number, runIds: number): Promise<{ requested: number; queued: number; jobs: ProcessingJob[] }>;
export function queueProjectRuns(projectId: number, runIds: number[]): Promise<{ requested: number; queued: number; jobs: ProcessingJob[] }>;
export function queueProjectRuns(
  projectId: number,
  runIds: number | number[],
  experimentId?: number,
): Promise<{ requested: number; queued: number; jobs: ProcessingJob[] }>;
export function queueProjectRuns(
  projectId: number,
  runIds: number | number[],
  experimentId?: number,
): Promise<{ requested: number; queued: number; jobs: ProcessingJob[] }> {
  return postResource(`/projects/${projectId}/queue-runs/`, {
    run_ids: Array.isArray(runIds) ? runIds : [runIds],
    ...(experimentId ? { experiment: experimentId } : {}),
  });
}

export function rerunLatestDiannBatch(projectId: number): Promise<{
  worklist_id: number;
  project_id: number;
  pipeline_id: number;
  converted: number;
  rerun: number;
  skipped: number;
}> {
  return postResource(`/projects/${projectId}/rerun-latest-diann-batch/`, {});
}

export function updateWorklistEntry(id: number, payload: Partial<AcquisitionWorklist> & Record<string, unknown>): Promise<unknown> {
  return patchResource(`/worklist-entries/${id}/`, payload);
}

export function updateRun(id: number, payload: Partial<Run>): Promise<Run> {
  return patchResource<Run>(`/runs/${id}/`, payload);
}

export function fetchRawFiles(params: ListParams): Promise<Paginated<RawFile>> {
  return paginatedResource<RawFile>("/raw-files/", { ordering: "-imported_at", ...params });
}

export function fetchRawFileDerivatives(params?: ListParams): Promise<Paginated<RawFileDerivative>> {
  return paginatedResource<RawFileDerivative>("/raw-file-derivatives/", { ordering: "-updated_at", ...params });
}

export function fetchRawFileSpectra(id: number, params?: ListParams): Promise<SpectraResponse> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<SpectraResponse>(`/raw-files/${id}/spectra/${query.toString() ? `?${query}` : ""}`);
}

export function fetchRawFileSpectrum(id: number, spectrumId: string): Promise<SpectrumDetailResponse> {
  return getResource<SpectrumDetailResponse>(`/raw-files/${id}/spectra/${encodeURIComponent(spectrumId)}/`);
}

export function fetchRawFileChromatograms(id: number): Promise<ChromatogramsResponse> {
  return getResource<ChromatogramsResponse>(`/raw-files/${id}/chromatograms/`);
}

export function fetchProcessingJobs(params: ListParams): Promise<Paginated<ProcessingJob>> {
  return paginatedResource<ProcessingJob>("/processing-jobs/", { ordering: "-created_at", ...params });
}

export function fetchProcessingJobsOverview(params?: ListParams): Promise<ProcessingJobOverview> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<ProcessingJobOverview>(`/processing-jobs/overview/${query.toString() ? `?${query}` : ""}`);
}

export function fetchProcessingNodes(params?: ListParams): Promise<Paginated<ProcessingNode>> {
  return paginatedResource<ProcessingNode>("/processing-nodes/", { ordering: "name", ...params });
}

export function fetchProcessingNodesOverview(params?: ListParams): Promise<ProcessingNodeOverview> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<ProcessingNodeOverview>(`/processing-nodes/overview/${query.toString() ? `?${query}` : ""}`);
}

export function fetchSystemHealth(): Promise<SystemHealthSnapshot> {
  return getResource<SystemHealthSnapshot>("/system-health/");
}

export function controlProcessingNode(
  id: number,
  payload: { command: "start" | "pause" | "resume" | "drain" | "restart" | "stop" | "upgrade" | "reconfigure"; reason?: string; parameters?: Record<string, unknown> },
): Promise<ProcessingNode> {
  return postResource<ProcessingNode>(`/processing-nodes/${id}/control/`, payload);
}

export function markProcessingNodeOffline(id: number, reason?: string): Promise<ProcessingNode> {
  return postResource<ProcessingNode>(`/processing-nodes/${id}/mark-offline/`, { reason: reason ?? "" });
}

export function fetchProcessingPipelines(params?: ListParams): Promise<Paginated<ProcessingPipeline>> {
  return paginatedResource<ProcessingPipeline>("/processing-pipelines/", { ordering: "name", ...params });
}

export function fetchDeploymentSettings(): Promise<DeploymentSettings> {
  return getResource<DeploymentSettings>("/deployment-settings/");
}

export function updateDeploymentSettings(
  payload: Partial<Pick<DeploymentSettings, "prtc_skyline_pipeline" | "targeted_skyline_pipeline" | "metadata">>,
) {
  return patchResource<DeploymentSettings>("/deployment-settings/", payload);
}

export function fetchDeploymentReleases(params?: ListParams): Promise<Paginated<DeploymentRelease>> {
  return paginatedResource<DeploymentRelease>("/deployment-releases/", { ordering: "-created_at", ...params });
}
export function createDeploymentRelease(payload: Partial<DeploymentRelease>): Promise<DeploymentRelease> {
  return postResource<DeploymentRelease>("/deployment-releases/", payload);
}
export function promoteDeploymentRelease(id: number): Promise<DeploymentRelease> {
  return postResource<DeploymentRelease>(`/deployment-releases/${id}/promote/`, {});
}
export function rolloutDeploymentRelease(id: number, node_ids?: number[]): Promise<unknown> {
  return postResource(`/deployment-releases/${id}/rollout/`, node_ids?.length ? { node_ids } : {});
}
export function verifyDeploymentRelease(id: number, rollback = true): Promise<unknown> {
  return postResource(`/deployment-releases/${id}/verify/`, { rollback });
}
export function fetchDeploymentReleaseAudit(): Promise<Array<{ id: number; created_at: string; message: string; actor_username?: string; payload: Record<string, unknown> }>> {
  return getResource("/deployment-releases/audit/");
}

export function fetchInstrumentConfigurations(params?: ListParams): Promise<Paginated<InstrumentConfiguration>> {
  return paginatedResource<InstrumentConfiguration>("/instrument-configurations/", { ordering: "name", ...params });
}

export function fetchRawFilesOverview(params?: ListParams): Promise<RawFileOverview> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<RawFileOverview>(`/raw-files/overview/${query.toString() ? `?${query}` : ""}`);
}

export function fetchSamples(params: ListParams): Promise<Paginated<Sample>> {
  return paginatedResource<Sample>("/samples/", { ordering: "name", ...params });
}

export function fetchRuns(params: ListParams): Promise<Paginated<Run>> {
  return paginatedResource<Run>("/runs/", { ordering: "worklist_position", ...params });
}

export function fetchRunSummary(id: number): Promise<RunSummary> {
  return getResource<RunSummary>(`/runs/${id}/summary/`);
}

export function fetchAcquisitions(params: ListParams): Promise<Paginated<AcquisitionWorklist>> {
  return paginatedResource<AcquisitionWorklist>("/acquisition-worklists/", { ordering: "-updated_at", ...params });
}

export function fetchQcOverview(params?: ListParams): Promise<QcOverview> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<QcOverview>(`/qc/overview/${query.toString() ? `?${query}` : ""}`);
}

export function fetchQcDetails(params?: ListParams): Promise<QcDetails> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return getResource<QcDetails>(`/qc/details/${query.toString() ? `?${query}` : ""}`);
}
