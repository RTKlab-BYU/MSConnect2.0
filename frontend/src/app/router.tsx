import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/shell/app-shell";
import { RoleGuard } from "@/components/shell/role-guard";
import { NotFoundRoute, RouteErrorBoundary, RouteFallback } from "@/components/shell/route-fallback";
import { isFacilityProfile } from "@/lib/instance-profile";

const SignupPage = lazy(() => import("@/features/auth/signup-page"));
const VerifyEmailPage = lazy(() => import("@/features/auth/verify-email-page"));
const AcceptInvitationPage = lazy(() => import("@/features/auth/accept-invitation-page"));
const AdminUserAccessPage = lazy(() => import("@/features/admin/user-access-page"));
const AdminLabsPage = lazy(() => import("@/features/admin/labs-page"));
const AdminGlobalSettingsPage = lazy(() => import("@/features/admin/global-settings-page"));
const AdminAssistantPage = lazy(() => import("@/features/admin/assistant-admin-page"));
const InstrumentConfigurationsPage = lazy(() => import("@/features/admin/instrument-configurations-page"));
const ProjectsPage = lazy(() => import("@/features/projects/projects-page"));
const ProjectWorkspacePage = lazy(() => import("@/features/projects/project-workspace-page"));
const SampleReportPage = lazy(() => import("@/features/projects/sample-report-page"));
const SubmissionWizardPage = lazy(() => import("@/features/intake/submission-wizard-page"));
const SubmissionsPage = lazy(() => import("@/features/intake/submissions-page"));
const SubmissionDetailPage = lazy(() => import("@/features/intake/submission-detail-page"));
const IntakeQueuePage = lazy(() => import("@/features/intake/intake-queue-page"));
const DashboardPage = lazy(() => import("@/features/dashboard/dashboard-page"));
const AdminDashboardPage = lazy(() => import("@/features/admin/admin-dashboard-page"));
const QcPage = lazy(() => import("@/features/qc/qc-page"));
const HyePairPage = lazy(() => import("@/features/qc/hye-pair-page"));
const MonitoringPage = lazy(() => import("@/features/monitoring/monitoring-page"));
const ProcessingPage = lazy(() => import("@/features/processing/processing-page"));
const ProcessingAdminPage = lazy(() => import("@/features/processing/processing-admin-page"));
const SpectraPage = lazy(() => import("@/features/spectra/spectra-page"));
const WatcherPage = lazy(() => import("@/features/watcher/watcher-page"));
const UploadsPage = lazy(() => import("@/features/uploads/uploads-page"));
const SettingsPage = lazy(() => import("@/features/settings/settings-page"));

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <Navigate to="/projects" replace />,
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "/project",
      element: <Navigate to="/projects" replace />,
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "signup",
      element: (
        <Suspense fallback={<RouteFallback label="Loading signup" />}>
          <SignupPage />
        </Suspense>
      ),
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "verify-email/:token",
      element: <Suspense fallback={<RouteFallback label="Verifying email" />}><VerifyEmailPage /></Suspense>,
      errorElement: <RouteErrorBoundary />,
    },
    {
      path: "accept-invite/:uid/:token",
      element: <Suspense fallback={<RouteFallback label="Loading invitation" />}><AcceptInvitationPage /></Suspense>,
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
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading admin dashboard" />}>
                <AdminDashboardPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "admin/users",
          element: (
            <RoleGuard allow={["admin"]}>
              <Suspense fallback={<RouteFallback label="Loading user access" />}><AdminUserAccessPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "admin/labs",
          element: (
            <RoleGuard allow={["admin"]}>
              <Suspense fallback={<RouteFallback label="Loading organization setup" />}><AdminLabsPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "admin/lc-ms",
          element: (
            <RoleGuard allow={["admin"]} allowFacilityManager>
              <Suspense fallback={<RouteFallback label="Loading LC-MS configurations" />}><InstrumentConfigurationsPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "admin/settings",
          element: (
            <RoleGuard allow={["admin"]}>
              <Suspense fallback={<RouteFallback label="Loading global settings" />}><AdminGlobalSettingsPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "admin/assistant",
          element: (
            <RoleGuard allow={["admin"]}>
              <Suspense fallback={<RouteFallback label="Loading AI agent settings" />}><AdminAssistantPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "intake",
          element: isFacilityProfile ? (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading intake queue" />}>
                <IntakeQueuePage />
              </Suspense>
            </RoleGuard>
          ) : <Navigate to="/projects" replace />,
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
          path: "worklist-generator",
          element: <Navigate to="/projects" replace />,
        },
        {
          path: "qc",
          element: (
            <Navigate to="/qc/hye" replace />
          ),
        },
        {
          path: "qc/hye",
          element: (
            <RoleGuard allow={["admin", "pi", "researcher", "collaborator"]}>
              <Suspense fallback={<RouteFallback label="Loading HYE QC workspace" />}><QcPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "qc/prtc",
          element: (
            <RoleGuard allow={["admin", "pi", "researcher", "collaborator"]}>
              <Suspense fallback={<RouteFallback label="Loading PRTC QC workspace" />}><QcPage /></Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "qc/hye/:worklistId/:pairLabel",
          element: (
            <RoleGuard allow={["admin", "pi", "researcher", "collaborator"]}>
              <Suspense fallback={<RouteFallback label="Loading HYE record" />}>
                <HyePairPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "monitoring",
          element: (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading monitoring dashboard" />}>
                <MonitoringPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "processing",
          element: (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading processing control" />}>
                <ProcessingPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "processing/admin",
          element: (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading processor admin" />}>
                <ProcessingAdminPage />
              </Suspense>
            </RoleGuard>
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
          path: "watcher",
          element: (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading watcher console" />}>
                <WatcherPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "uploads",
          element: (
            <RoleGuard allow={["admin", "pi"]}>
              <Suspense fallback={<RouteFallback label="Loading uploads" />}>
                <UploadsPage />
              </Suspense>
            </RoleGuard>
          ),
        },
        {
          path: "submissions",
          element: isFacilityProfile ? (
            <Suspense fallback={<RouteFallback label="Loading submissions" />}>
              <SubmissionsPage />
            </Suspense>
          ) : <Navigate to="/projects" replace />,
        },
        {
          path: "submissions/new",
          element: isFacilityProfile ? (
            <Suspense fallback={<RouteFallback label="Loading submission wizard" />}>
              <SubmissionWizardPage />
            </Suspense>
          ) : <Navigate to="/projects" replace />,
        },
        {
          path: "submissions/:submissionId",
          element: isFacilityProfile ? (
            <Suspense fallback={<RouteFallback label="Loading submission detail" />}>
              <SubmissionDetailPage />
            </Suspense>
          ) : <Navigate to="/projects" replace />,
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
          path: "projects/:projectId/:section",
          element: (
            <Suspense fallback={<RouteFallback label="Loading project workspace" />}>
              <ProjectWorkspacePage />
            </Suspense>
          ),
        },
        {
          path: "projects/:projectId/experiments/:experimentId",
          element: (
            <Suspense fallback={<RouteFallback label="Loading experiment workspace" />}>
              <ProjectWorkspacePage />
            </Suspense>
          ),
        },
        {
          path: "projects/:projectId/experiments/:experimentId/:section",
          element: (
            <Suspense fallback={<RouteFallback label="Loading experiment workspace" />}>
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
            <RoleGuard allow={["admin"]}>
              <Suspense fallback={<RouteFallback label="Loading settings" />}>
                <SettingsPage />
              </Suspense>
            </RoleGuard>
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
