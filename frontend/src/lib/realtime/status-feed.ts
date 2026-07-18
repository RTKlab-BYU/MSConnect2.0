import { useQuery } from "@tanstack/react-query";

import {
  fetchProcessingJobs,
  fetchProcessingJobsOverview,
  fetchProcessingNodes,
  fetchProcessingNodesOverview,
  fetchRawFilesOverview,
  queryKeys,
} from "@/lib/api/queries";

const DASHBOARD_POLL_MS = 20_000;

function jitter() {
  return Math.round(Math.random() * 4_000);
}

export function useRunStatusFeed(projectId?: number) {
  const params = projectId ? { project: projectId } : {};
  const interval = DASHBOARD_POLL_MS + jitter();
  const jobsOverview = useQuery({
    queryKey: queryKeys.processingJobsOverview(params),
    queryFn: () => fetchProcessingJobsOverview(params),
    refetchInterval: interval,
  });
  const nodesOverview = useQuery({
    queryKey: queryKeys.processingNodesOverview(),
    queryFn: () => fetchProcessingNodesOverview(),
    refetchInterval: interval + 2_000,
  });
  const rawFilesOverview = useQuery({
    queryKey: queryKeys.rawFilesOverview(params),
    queryFn: () => fetchRawFilesOverview(params),
    refetchInterval: interval + 4_000,
  });
  const activeJobs = useQuery({
    queryKey: queryKeys.processingJobs({ ...params, active: true, page: 1, page_size: 100 }),
    queryFn: () => fetchProcessingJobs({ ...params, active: true, page: 1, page_size: 100 }),
    refetchInterval: interval,
  });
  const nodes = useQuery({
    queryKey: queryKeys.processingNodes({ page: 1, page_size: 100 }),
    queryFn: () => fetchProcessingNodes({ page: 1, page_size: 100 }),
    refetchInterval: interval + 2_000,
  });

  const hasError =
    jobsOverview.isError || nodesOverview.isError || rawFilesOverview.isError || activeJobs.isError || nodes.isError;

  return {
    transport: "polling" as const,
    connected: !hasError,
    reconnecting: hasError && (jobsOverview.isFetching || nodesOverview.isFetching || rawFilesOverview.isFetching),
    lastUpdatedAt: Math.max(
      jobsOverview.dataUpdatedAt,
      nodesOverview.dataUpdatedAt,
      rawFilesOverview.dataUpdatedAt,
      activeJobs.dataUpdatedAt,
      nodes.dataUpdatedAt,
    ),
    jobsOverview: jobsOverview.data,
    nodesOverview: nodesOverview.data,
    rawFilesOverview: rawFilesOverview.data,
    activeJobs: activeJobs.data?.results ?? [],
    nodes: nodes.data?.results ?? [],
    isLoading:
      jobsOverview.isLoading || nodesOverview.isLoading || rawFilesOverview.isLoading || activeJobs.isLoading || nodes.isLoading,
  };
}
