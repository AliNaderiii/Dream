/** Route table for the Dream desktop shell. */

import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/app-shell';
import { ChatRoute } from '@/routes/chat';
import { DashboardRoute } from '@/routes/dashboard';
import { MemoryRoute } from '@/routes/memory';
import { ProjectsRoute } from '@/routes/projects';
import { ProvidersRoute } from '@/routes/providers';
import { SettingsRoute } from '@/routes/settings';
import { SkillsRoute } from '@/routes/skills';

// Heavy screens are code-split so the shell paints before their chunks load.
// Each lazy route resolves the named export to a default export for React.lazy.
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
  return <div className="flex h-full items-center justify-center text-fg-muted" />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardRoute />} />
        <Route path="chat/:sessionId" element={<ChatRoute />} />
        <Route path="chat" element={<ChatRoute />} />
        <Route path="memory" element={<MemoryRoute />} />
        <Route path="skills" element={<SkillsRoute />} />
        <Route path="projects" element={<ProjectsRoute />} />
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
        <Route path="providers" element={<ProvidersRoute />} />
        <Route path="settings" element={<SettingsRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
