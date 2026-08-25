import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { getSeedRootId, resetEchoWorkspace } from './echo-workspace';
import {
  workspaceContinue,
  workspaceFilesList,
  workspaceFilesPreview,
  workspaceGoal,
  workspaceImportFolder,
  workspacePlan,
  workspaceRefsParse,
  workspaceRootsList,
  workspaceShellExecute,
  workspaceShellPropose,
  workspaceStatus,
  workspaceStop,
  workspaceSubagentsLive,
} from './workspace';

describe('workspace echo wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkspace();
  });

  it('lists the seeded in-place root and never marks it copied', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const listed = await workspaceRootsList(client);
    expect(listed.roots[0]?.copied).toBe(false);
    expect(listed.roots[0]?.imported_in_place).toBe(true);
  });

  it('previews a CSV with a chart and refuses traversal', async () => {
    const client = getBridgeClient();
    const preview = await workspaceFilesPreview(client, getSeedRootId(), 'sales.csv');
    expect(preview.executed).toBe(false);
    expect(preview.chart?.kind).toBe('bar');
    expect(preview.chart?.labels).toContain('North');
    await expect(workspaceFilesPreview(client, getSeedRootId(), '../secret')).rejects.toThrow(
      /traversal/,
    );
  });

  it('plans then executes on continue, and stop reports live state', async () => {
    const client = getBridgeClient();
    const plan = await workspacePlan(client, 'Summarise sales');
    expect(plan.status).toBe('pending_approval');
    const continued = await workspaceContinue(client, plan.plan_id);
    expect(continued.executed).toBe(true);
    const stopped = await workspaceStop(client);
    expect(stopped.stopped).toBe(true);
    expect(stopped.live).toBe(true);
    const status = await workspaceStatus(client);
    expect(status.live).toBe(true);
  });

  it('reports an honest inability for an impossible goal', async () => {
    const client = getBridgeClient();
    const goal = await workspaceGoal(client, 'Keep tables honest', [
      'CSV has a chart',
      'must fetch live market prices',
    ]);
    expect(goal.status).toBe('unable');
    expect(goal.report).toMatch(/could not meet/);
  });

  it('parses @file #conversation /commands and !shell', async () => {
    const client = getBridgeClient();
    const parsed = await workspaceRefsParse(client, 'see @sales.csv and #sess_1 /plan !ls');
    expect(parsed.files).toContain('sales.csv');
    expect(parsed.conversations).toContain('sess_1');
    expect(parsed.commands).toContain('plan');
    expect(parsed.shell.length).toBeGreaterThan(0);
    const proposal = await workspaceShellPropose(client, 'rm -rf /');
    expect(proposal.risk).toBe('dangerous');
    expect(proposal.network).toBe(false);
    const executed = await workspaceShellExecute(client, proposal.approval_id, true);
    expect(executed.executed).toBe(false);
  });

  it('lists nested notes entries and reports unverifiable goals honestly', async () => {
    const client = getBridgeClient();
    const listing = await workspaceFilesList(client, getSeedRootId(), 'notes');
    expect(listing.entries.some((entry) => entry.name === 'todo.md')).toBe(true);
    const goal = await workspaceGoal(client, 'Document the folder', [
      'README exists',
      'teleport the files to Mars',
    ]);
    expect(goal.status).toBe('unable');
    expect(goal.results.find((row) => row.criterion === 'README exists')?.met).toBe(true);
    expect(goal.results.find((row) => row.criterion.includes('Mars'))?.met).toBe(false);
  });

  it('imports a folder in place without copying', async () => {
    const client = getBridgeClient();
    const imported = await workspaceImportFolder(client, '/work/lab', 'Lab');
    expect(imported.copied).toBe(false);
    const live = await workspaceSubagentsLive(client);
    expect(live.live).toBe(true);
  });
});
