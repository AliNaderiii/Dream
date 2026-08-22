/** Route table for the Dream desktop shell. */

import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/app-shell';

// Workspaces are code-split so the shell paints before their chunks load.
// Each lazy route resolves the named export to a default export for React.lazy.
const DashboardRoute = lazy(() =>
  import('@/routes/dashboard').then((m) => ({ default: m.DashboardRoute })),
);
const ChatRoute = lazy(() => import('@/routes/chat').then((m) => ({ default: m.ChatRoute })));
const MemoryRoute = lazy(() => import('@/routes/memory').then((m) => ({ default: m.MemoryRoute })));
const ProjectsRoute = lazy(() =>
  import('@/routes/projects').then((m) => ({ default: m.ProjectsRoute })),
);
const ProvidersRoute = lazy(() =>
  import('@/routes/providers').then((m) => ({ default: m.ProvidersRoute })),
);
const SettingsRoute = lazy(() =>
  import('@/routes/settings').then((m) => ({ default: m.SettingsRoute })),
);
const SkillsRoute = lazy(() => import('@/routes/skills').then((m) => ({ default: m.SkillsRoute })));
const ConnectivityRoute = lazy(() =>
  import('@/routes/connectivity').then((m) => ({ default: m.ConnectivityRoute })),
);
const DataRoute = lazy(() => import('@/routes/data').then((m) => ({ default: m.DataRoute })));
const DataDatasetRoute = lazy(() =>
  import('@/routes/data.dataset').then((m) => ({ default: m.DataDatasetRoute })),
);
const ProvenanceRoute = lazy(() =>
  import('@/routes/provenance').then((m) => ({ default: m.ProvenanceRoute })),
);
const SchedulerRoute = lazy(() =>
  import('@/routes/scheduler').then((m) => ({ default: m.SchedulerRoute })),
);
const SubagentsRoute = lazy(() =>
  import('@/routes/subagents').then((m) => ({ default: m.SubagentsRoute })),
);

/** Lightweight fallback shown while a lazy chunk is still loading. */
function RouteFallback() {
  return (
    <div
      role="status"
      aria-busy="true"
      className="flex h-full flex-col gap-3 p-6 motion-reduce:animate-none"
    >
      <div className="skeleton-shape h-8 w-48 rounded-lg" />
      <div className="skeleton-shape h-24 w-full rounded-xl" />
      <div className="skeleton-shape h-24 w-full rounded-xl" />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          index
          element={
            <Suspense fallback={<RouteFallback />}>
              <DashboardRoute />
            </Suspense>
          }
        />
        <Route
          path="chat/:sessionId"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ChatRoute />
            </Suspense>
          }
        />
        <Route
          path="chat"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ChatRoute />
            </Suspense>
          }
        />
        <Route
          path="memory"
          element={
            <Suspense fallback={<RouteFallback />}>
              <MemoryRoute />
            </Suspense>
          }
        />
        <Route
          path="skills"
          element={
            <Suspense fallback={<RouteFallback />}>
              <SkillsRoute />
            </Suspense>
          }
        />
        <Route
          path="projects"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ProjectsRoute />
            </Suspense>
          }
        />
        <Route
          path="scheduler"
          element={
            <Suspense fallback={<RouteFallback />}>
              <SchedulerRoute />
            </Suspense>
          }
        />
        <Route
          path="subagents"
          element={
            <Suspense fallback={<RouteFallback />}>
              <SubagentsRoute />
            </Suspense>
          }
        />
        <Route
          path="provenance"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ProvenanceRoute />
            </Suspense>
          }
        />
        <Route
          path="data"
          element={
            <Suspense fallback={<RouteFallback />}>
              <DataRoute />
            </Suspense>
          }
        />
        <Route
          path="data/:datasetId"
          element={
            <Suspense fallback={<RouteFallback />}>
              <DataDatasetRoute />
            </Suspense>
          }
        />
        <Route
          path="connectivity"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ConnectivityRoute />
            </Suspense>
          }
        />
        <Route
          path="providers"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ProvidersRoute />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<RouteFallback />}>
              <SettingsRoute />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
