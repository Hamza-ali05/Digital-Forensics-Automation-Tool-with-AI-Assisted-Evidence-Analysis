import React, { lazy, Suspense } from "react";
import { Redirect, Route, Switch } from "react-router-dom";

import AuthGuard from "guards/AuthGuard";
import GuestGuard from "guards/GuestGuard";
import RoleGuard from "guards/RoleGuard";
import DashboardLayout from "layouts/DashboardLayout";
import AuthLayout from "layouts/AuthLayout";
import MinimalLayout from "layouts/MinimalLayout";
import LoadingSpinner from "components/common/LoadingSpinner";

/**
 * Path registry for navigation links (Sidebar, Topbar, auth pages).
 */
export const Routes = {
  Dashboard: { path: "/dashboard" },
  Cases: { path: "/cases" },
  CasesNew: { path: "/cases/new" },
  CaseDetail: { path: "/cases/:id" },
  Evidence: { path: "/evidence" },
  EvidenceRegister: { path: "/evidence/register" },
  EvidenceIntegrity: { path: "/evidence/integrity" },
  EvidenceDetail: { path: "/evidence/:id" },
  Pipeline: { path: "/pipeline" },
  PipelineRun: { path: "/pipeline/run" },
  PipelineDetail: { path: "/pipeline/:jobId" },
  Artefacts: { path: "/artefacts/:id" },
  ArtefactsTimeline: { path: "/artefacts/timeline" },
  ArtefactsIOCs: { path: "/artefacts/iocs" },
  AIAnalysis: { path: "/ai" },
  AISummary: { path: "/ai/summary" },
  Reports: { path: "/reports" },
  JSONViewer: { path: "/reports/json" },
  ReportDetail: { path: "/reports/:id" },
  Evaluation: { path: "/evaluation" },
  EvaluationBenchmark: { path: "/evaluation/benchmark" },
  EvaluationBenchmarkHistory: { path: "/evaluation/benchmark/history" },
  EvaluationPerformance: { path: "/evaluation/performance" },
  EvaluationUsability: { path: "/evaluation/usability" },
    Settings: { path: "/settings" },
  SettingsUsers: { path: "/settings/users" },
  Profile: { path: "/profile" },
  Questionnaire: { path: "/questionnaire" },
  Login: { path: "/auth/login" },
  Register: { path: "/auth/register" },
  NotFound: { path: "/404" },
  ServerError: { path: "/500" },
};

// Lazy-loaded pages (code splitting — Prompt 8 fills real UIs)
const Dashboard = lazy(() => import("pages/Dashboard"));
const Login = lazy(() => import("pages/auth/Login"));
const Register = lazy(() => import("pages/auth/Register"));
const NotFound = lazy(() => import("pages/errors/NotFound"));
const ServerError = lazy(() => import("pages/errors/ServerError"));
const Questionnaire = lazy(() => import("pages/evaluation/Questionnaire"));
const CaseList = lazy(() => import("pages/cases/CaseList"));
const CaseCreate = lazy(() => import("pages/cases/CaseCreate"));
const CaseDetail = lazy(() => import("pages/cases/CaseDetail"));
const EvidenceInventory = lazy(() => import("pages/evidence/EvidenceInventory"));
const EvidenceRegister = lazy(() => import("pages/evidence/EvidenceRegister"));
const EvidenceIntegrity = lazy(() => import("pages/evidence/IntegrityCheck"));
const EvidenceDetail = lazy(() => import("pages/evidence/EvidenceDetail"));
const PipelineJobs = lazy(() => import("pages/pipeline/PipelineJobs"));
const PipelineRun = lazy(() => import("pages/pipeline/PipelineRun"));
const PipelineDetail = lazy(() => import("pages/pipeline/PipelineDetail"));
const ArtefactExplorer = lazy(() => import("pages/artefacts/ArtefactExplorer"));
const TimelinePage = lazy(() => import("pages/artefacts/TimelinePage"));
const IOCDashboard = lazy(() => import("pages/artefacts/IOCDashboard"));
const AIAnalysis = lazy(() => import("pages/ai/AIAnalysis"));
const AISummaryViewer = lazy(() => import("pages/ai/AISummaryViewer"));
const ReportList = lazy(() => import("pages/reports/ReportList"));
const JSONViewer = lazy(() => import("pages/reports/JSONViewer"));
const ReportDetail = lazy(() => import("pages/reports/ReportDetail"));
const EvaluationDashboard = lazy(() =>
  import("pages/evaluation/EvaluationDashboard")
);
const BenchmarkRun = lazy(() => import("pages/evaluation/BenchmarkRun"));
const BenchmarkResults = lazy(() =>
  import("pages/evaluation/BenchmarkResults")
);
const PerformanceDashboard = lazy(() =>
  import("pages/evaluation/PerformanceDashboard")
);
const UsabilityResults = lazy(() =>
  import("pages/evaluation/UsabilityResults")
);
const Settings = lazy(() => import("pages/settings/Settings"));
const UserManagement = lazy(() => import("pages/settings/UserManagement"));
const Profile = lazy(() => import("pages/Profile"));

const withSuspense = (node) => (
  <Suspense fallback={<LoadingSpinner show />}>{node}</Suspense>
);

/**
 * Authenticated dashboard shell with nested RR5 routes.
 * Mirrors the Prompt 7.9 children tree (RR6-style) on React Router 5.
 */
function ProtectedApp() {
  return (
    <AuthGuard>
      <DashboardLayout>
        {withSuspense(
          <Switch>
            <Redirect exact from="/" to={Routes.Dashboard.path} />
            <Route exact path={Routes.Dashboard.path} component={Dashboard} />
            <Route exact path={Routes.Profile.path} component={Profile} />

            <Route
              exact
              path={Routes.CasesNew.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator"]}>
                  <CaseCreate />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.CaseDetail.path}
              component={CaseDetail}
            />
            <Route
              exact
              path={Routes.Cases.path}
              render={() => (
                <RoleGuard
                  allowedRoles={["admin", "investigator", "analyst"]}
                >
                  <CaseList />
                </RoleGuard>
              )}
            />

            <Route
              exact
              path={Routes.EvidenceRegister.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator"]}>
                  <EvidenceRegister />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.EvidenceIntegrity.path}
              render={() => (
                <RoleGuard
                  allowedRoles={["admin", "investigator", "analyst"]}
                >
                  <EvidenceIntegrity />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.EvidenceDetail.path}
              component={EvidenceDetail}
            />
            <Route
              exact
              path={Routes.Evidence.path}
              render={() => (
                <RoleGuard
                  allowedRoles={["admin", "investigator", "analyst"]}
                >
                  <EvidenceInventory />
                </RoleGuard>
              )}
            />

            <Route
              exact
              path={Routes.PipelineRun.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator", "analyst"]}>
                  <PipelineRun />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.PipelineDetail.path}
              component={PipelineDetail}
            />
            <Route
              exact
              path={Routes.Pipeline.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator", "analyst"]}>
                  <PipelineJobs />
                </RoleGuard>
              )}
            />

            <Route
              exact
              path={Routes.ArtefactsTimeline.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator", "analyst"]}>
                  <TimelinePage />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.ArtefactsIOCs.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator", "analyst"]}>
                  <IOCDashboard />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.Artefacts.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator", "analyst"]}>
                  <ArtefactExplorer />
                </RoleGuard>
              )}
            />

            <Route exact path={Routes.AIAnalysis.path} component={AIAnalysis} />
            <Route
              exact
              path={Routes.AISummary.path}
              component={AISummaryViewer}
            />

            <Route
              exact
              path={Routes.JSONViewer.path}
              component={JSONViewer}
            />
            <Route
              exact
              path={Routes.ReportDetail.path}
              component={ReportDetail}
            />
            <Route exact path={Routes.Reports.path} component={ReportList} />

            <Route
              exact
              path={Routes.EvaluationBenchmarkHistory.path}
              component={BenchmarkResults}
            />
            <Route
              exact
              path={Routes.EvaluationBenchmark.path}
              component={BenchmarkRun}
            />
            <Route
              exact
              path={Routes.EvaluationPerformance.path}
              component={PerformanceDashboard}
            />
            <Route
              exact
              path={Routes.EvaluationUsability.path}
              render={() => (
                <RoleGuard allowedRoles={["admin", "investigator"]}>
                  <UsabilityResults />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.Evaluation.path}
              component={EvaluationDashboard}
            />

            <Route
              exact
              path={Routes.SettingsUsers.path}
              render={() => (
                <RoleGuard allowedRoles={["admin"]}>
                  <UserManagement />
                </RoleGuard>
              )}
            />
            <Route
              exact
              path={Routes.Settings.path}
              render={() => (
                <RoleGuard allowedRoles={["admin"]}>
                  <Settings />
                </RoleGuard>
              )}
            />

            <Redirect to={Routes.NotFound.path} />
          </Switch>
        )}
      </DashboardLayout>
    </AuthGuard>
  );
}

/**
 * Top-level route tree used by App.js.
 * React Router 5 equivalent of the Prompt 7.9 `routes` / `useRoutes` config.
 */
export function AppRoutes() {
  return (
    <Switch>
      <Route
        exact
        path={Routes.Login.path}
        render={() =>
          withSuspense(
            <GuestGuard>
              <AuthLayout>
                <Login />
              </AuthLayout>
            </GuestGuard>
          )
        }
      />
      <Route
        exact
        path={Routes.Register.path}
        render={() =>
          withSuspense(
            <AuthGuard>
              <RoleGuard allowedRoles={["admin", "investigator"]}>
                <AuthLayout>
                  <Register />
                </AuthLayout>
              </RoleGuard>
            </AuthGuard>
          )
        }
      />

      {/* Public usability questionnaire — no auth (ethics). */}
      <Route
        exact
        path={Routes.Questionnaire.path}
        render={() =>
          withSuspense(
            <MinimalLayout>
              <Questionnaire />
            </MinimalLayout>
          )
        }
      />

      <Route
        exact
        path={Routes.NotFound.path}
        render={() =>
          withSuspense(
            <MinimalLayout>
              <NotFound />
            </MinimalLayout>
          )
        }
      />
      <Route
        exact
        path={Routes.ServerError.path}
        render={() =>
          withSuspense(
            <MinimalLayout>
              <ServerError />
            </MinimalLayout>
          )
        }
      />

      {/* Protected app (dashboard + forensic pages) */}
      <Route path="/" component={ProtectedApp} />
    </Switch>
  );
}

export default AppRoutes;
