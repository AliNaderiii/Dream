/** Route table for the Dream desktop shell. */

import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/app-shell';
import { ChatRoute } from '@/routes/chat';
import { DashboardRoute } from '@/routes/dashboard';
import { DataRoute } from '@/routes/data';
import { MemoryRoute } from '@/routes/memory';
import { ProjectsRoute } from '@/routes/projects';
import { ProvenanceRoute } from '@/routes/provenance';
import { ProvidersRoute } from '@/routes/providers';
import { SettingsRoute } from '@/routes/settings';
import { SkillsRoute } from '@/routes/skills';
import { SubagentsRoute } from '@/routes/subagents';

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
        <Route path="subagents" element={<SubagentsRoute />} />
        <Route path="provenance" element={<ProvenanceRoute />} />
        <Route path="data" element={<DataRoute />} />
        <Route path="providers" element={<ProvidersRoute />} />
        <Route path="settings" element={<SettingsRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
