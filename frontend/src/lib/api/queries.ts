import { getResource, paginatedResource, postResource, type ListParams } from "@/lib/api/client";
import type {
  AcquisitionWorklist,
  ChromatogramsResponse,
  InstrumentConfiguration,
  Paginated,
  PreAcquisitionSetupPayload,
  PreAcquisitionSetupResponse,
  ProcessingJob,
  ProcessingJobOverview,
  ProcessingNode,
  ProcessingNodeOverview,
  ProcessingPipeline,
  Project,
  ProjectSummary,
  QcDetails,
  QcOverview,
  RawFile,
  RawFileDerivative,
  RawFileOverview,
  Run,
  RunSummary,
  Sample,
  SpectraResponse,
  SpectrumDetailResponse,
} from "@/lib/api/types";

export const queryKeys = {
  projects: (params?: ListParams) => ["projects", params] as const,
  project: (id: number) => ["project", id] as const,
  projectSummary: (id: number) => ["project", id, "summary"] as const,
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
  instrumentConfigurations: (params?: ListParams) => ["instrument-configurations", params] as const,
  samples: (params: ListParams) => ["samples", params] as const,
  runs: (params: ListParams) => ["runs", params] as const,
  runSummary: (id: number) => ["runs", id, "summary"] as const,
  acquisitions: (params: ListParams) => ["acquisition-worklists", params] as const,
  qcOverview: (params?: ListParams) => ["qc", "overview", params] as const,
  qcDetails: (params?: ListParams) => ["qc", "details", params] as const,
};

export function fetchProjects(params?: ListParams): Promise<Paginated<Project>> {
  return paginatedResource<Project>("/projects/", { ordering: "code", ...params });
}

export function fetchProject(id: number): Promise<Project> {
  return getResource<Project>(`/projects/${id}/`);
}

export function fetchProjectSummary(id: number): Promise<ProjectSummary> {
  return getResource<ProjectSummary>(`/projects/${id}/summary/`);
}

export function createPreAcquisitionSetup(payload: PreAcquisitionSetupPayload): Promise<PreAcquisitionSetupResponse> {
  return postResource<PreAcquisitionSetupResponse>("/projects/pre-acquisition-setup/", payload);
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

export function fetchProcessingPipelines(params?: ListParams): Promise<Paginated<ProcessingPipeline>> {
  return paginatedResource<ProcessingPipeline>("/processing-pipelines/", { ordering: "name", ...params });
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
