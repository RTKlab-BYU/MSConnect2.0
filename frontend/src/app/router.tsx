import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/shell/app-shell";
import { RouteFallback } from "@/components/shell/route-fallback";

const ProjectsPage = lazy(() => import("@/features/projects/projects-page"));
const ProjectWorkspacePage = lazy(() => import("@/features/projects/project-workspace-page"));
const QcPage = lazy(() => import("@/features/qc/qc-page"));
const MonitoringPage = lazy(() => import("@/features/monitoring/monitoring-page"));
const ProcessingPage = lazy(() => import("@/features/processing/processing-page"));
const UploadsPage = lazy(() => import("@/features/uploads/uploads-page"));
const SettingsPage = lazy(() => import("@/features/settings/settings-page"));

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <Navigate to="/projects" replace />,
    },
    {
      path: "/",
      element: <AppShell />,
      children: [
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
          path: "settings",
          element: (
            <Suspense fallback={<RouteFallback label="Loading settings" />}>
              <SettingsPage />
            </Suspense>
          ),
        },
      ],
    },
  ],
  { basename: "/app" },
);
