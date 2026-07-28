import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/shell/app-shell";
import { NotFoundRoute, RouteErrorBoundary, RouteFallback } from "@/components/shell/route-fallback";

const ProjectsPage = lazy(() => import("@/features/projects/projects-page"));
const ProjectWorkspacePage = lazy(() => import("@/features/projects/project-workspace-page"));
const SampleReportPage = lazy(() => import("@/features/projects/sample-report-page"));
const DashboardPage = lazy(() => import("@/features/dashboard/dashboard-page"));
const AdminDashboardPage = lazy(() => import("@/features/admin/admin-dashboard-page"));
const QcPage = lazy(() => import("@/features/qc/qc-page"));
const MonitoringPage = lazy(() => import("@/features/monitoring/monitoring-page"));
const ProcessingPage = lazy(() => import("@/features/processing/processing-page"));
const ProcessingAdminPage = lazy(() => import("@/features/processing/processing-admin-page"));
const SpectraPage = lazy(() => import("@/features/spectra/spectra-page"));
const UploadsPage = lazy(() => import("@/features/uploads/uploads-page"));
const SettingsPage = lazy(() => import("@/features/settings/settings-page"));

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <Navigate to="/dashboard" replace />,
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "/project",
      element: <Navigate to="/projects" replace />,
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "/",
      element: <AppShell />,
      errorElement: <RouteErrorBoundary />,
      children: [
        {
          path: "dashboard",
          element: (
            <Suspense fallback={<RouteFallback label="Loading dashboard" />}>
              <DashboardPage />
            </Suspense>
          ),
        },
        {
          path: "admin",
          element: (
            <Suspense fallback={<RouteFallback label="Loading admin dashboard" />}>
              <AdminDashboardPage />
            </Suspense>
          ),
        },
        {
          path: "projects",
          element: (
            <Suspense fallback={<RouteFallback label="Loading projects" />}>
              <ProjectsPage />
            </Suspense>
          ),
        },
        {
          path: "qc",
          element: (
            <Suspense fallback={<RouteFallback label="Loading QC workspace" />}>
              <QcPage />
            </Suspense>
          ),
        },
        {
          path: "monitoring",
          element: (
            <Suspense fallback={<RouteFallback label="Loading monitoring dashboard" />}>
              <MonitoringPage />
            </Suspense>
          ),
        },
        {
          path: "processing",
          element: (
            <Suspense fallback={<RouteFallback label="Loading processing control" />}>
              <ProcessingPage />
            </Suspense>
          ),
        },
        {
          path: "processing/admin",
          element: (
            <Suspense fallback={<RouteFallback label="Loading processor admin" />}>
              <ProcessingAdminPage />
            </Suspense>
          ),
        },
        {
          path: "spectra",
          element: (
            <Suspense fallback={<RouteFallback label="Loading spectra viewer" />}>
              <SpectraPage />
            </Suspense>
          ),
        },
        {
          path: "uploads",
          element: (
            <Suspense fallback={<RouteFallback label="Loading upload manager" />}>
              <UploadsPage />
            </Suspense>
          ),
        },
        {
          path: "projects/:projectId",
          element: (
            <Suspense fallback={<RouteFallback label="Loading project workspace" />}>
              <ProjectWorkspacePage />
            </Suspense>
          ),
        },
        {
          path: "projects/:projectId/samples/:sampleId",
          element: (
            <Suspense fallback={<RouteFallback label="Loading sample report" />}>
              <SampleReportPage />
            </Suspense>
          ),
        },
        {
          path: "settings",
          element: (
            <Suspense fallback={<RouteFallback label="Loading settings" />}>
              <SettingsPage />
            </Suspense>
          ),
        },
        {
          path: "*",
          element: <NotFoundRoute />,
        },
      ],
    },
  ],
  { basename: "/app" },
);
