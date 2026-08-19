/**
 * Echo `project.*` runtime (S06) — the offline contract the projects screen
 * relies on: wire shapes, validation errors, one-project-per-session, and
 * delete-ungroups-never-destroys.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { EchoBridgeTransport } from '@/lib/bridge/client';
import { RPC_ERROR } from '@/lib/bridge/types';
import type { BridgeProject, ProjectListResult } from '@/lib/bridge/types';

describe('EchoBridgeTransport projects', () => {
  let t: EchoBridgeTransport;

  beforeEach(() => {
    t = new EchoBridgeTransport();
  });

  it('creates, lists and deletes a project', async () => {
    const created = await t.request<BridgeProject>('1', 'project.create', {
      name: '  Thesis  ',
      folder: '/work/thesis',
    });
    expect(created.project_id).toMatch(/^prj_/);
    expect(created.id).toBe(created.project_id);
    expect(created.name).toBe('Thesis');
    expect(created.folder).toBe('/work/thesis');
    expect(created.session_ids).toEqual([]);

    const listed = await t.request<ProjectListResult>('2', 'project.list', {});
    expect(listed.projects.map((p) => p.name)).toEqual(['Thesis']);

    const deleted = await t.request<{ deleted: boolean }>('3', 'project.delete', {
      project_id: created.project_id,
    });
    expect(deleted.deleted).toBe(true);
    const after = await t.request<ProjectListResult>('4', 'project.list', {});
    expect(after.projects).toEqual([]);
  });

  it('rejects the same bad input the sidecar rejects', async () => {
    await expect(t.request('1', 'project.create', { name: '   ' })).rejects.toMatchObject({
      code: RPC_ERROR.INVALID_PARAMS,
    });
    await expect(
      t.request('2', 'project.create', { name: 'P', folder: '  ' }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });
    await expect(
      t.request('3', 'project.create', { name: 'P', session_ids: 'nope' }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });
    await expect(
      t.request('4', 'project.get', { project_id: 'prj_missing' }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });
  });

  it('only groups sessions the echo transport knows', async () => {
    const project = await t.request<BridgeProject>('1', 'project.create', { name: 'P' });
    await expect(
      t.request('2', 'project.add_session', {
        project_id: project.project_id,
        session_id: 'sess_ghost',
      }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });

    const session = await t.request<{ session_id: string }>('3', 'session.create', {
      title: 'real',
    });
    const updated = await t.request<BridgeProject>('4', 'project.add_session', {
      project_id: project.project_id,
      session_id: session.session_id,
    });
    expect(updated.session_ids).toEqual([session.session_id]);
  });

  it('a session belongs to one project at a time', async () => {
    const session = await t.request<{ session_id: string }>('1', 'session.create', {
      title: 'shared',
    });
    const first = await t.request<BridgeProject>('2', 'project.create', {
      name: 'First',
      session_ids: [session.session_id],
    });
    const second = await t.request<BridgeProject>('3', 'project.create', { name: 'Second' });

    await t.request('4', 'project.add_session', {
      project_id: second.project_id,
      session_id: session.session_id,
    });

    const firstAfter = await t.request<BridgeProject>('5', 'project.get', {
      project_id: first.project_id,
    });
    const secondAfter = await t.request<BridgeProject>('6', 'project.get', {
      project_id: second.project_id,
    });
    expect(firstAfter.session_ids).toEqual([]);
    expect(secondAfter.session_ids).toEqual([session.session_id]);
  });

  it('removing a session keeps it alive in the session list', async () => {
    const session = await t.request<{ session_id: string }>('1', 'session.create', {
      title: 'keeper',
    });
    const project = await t.request<BridgeProject>('2', 'project.create', {
      name: 'P',
      session_ids: [session.session_id],
    });

    await t.request('3', 'project.remove_session', {
      project_id: project.project_id,
      session_id: session.session_id,
    });

    const sessions = await t.request<{ sessions: Array<{ id: string }> }>('4', 'session.list', {});
    expect(sessions.sessions.map((s) => s.id)).toContain(session.session_id);
  });

  it('deleting a project never deletes its sessions', async () => {
    const session = await t.request<{ session_id: string }>('1', 'session.create', {
      title: 'survivor',
    });
    const project = await t.request<BridgeProject>('2', 'project.create', {
      name: 'P',
      session_ids: [session.session_id],
    });
    await t.request('3', 'project.delete', { project_id: project.project_id });

    const sessions = await t.request<{ sessions: Array<{ id: string }> }>('4', 'session.list', {});
    expect(sessions.sessions.map((s) => s.id)).toContain(session.session_id);
  });

  it('updates name and folder, clearing the folder with null', async () => {
    const project = await t.request<BridgeProject>('1', 'project.create', {
      name: 'Draft',
      folder: '/tmp/a',
    });
    const renamed = await t.request<BridgeProject>('2', 'project.update', {
      project_id: project.project_id,
      name: 'Final',
      folder: '/tmp/b',
    });
    expect(renamed.name).toBe('Final');
    expect(renamed.folder).toBe('/tmp/b');

    const cleared = await t.request<BridgeProject>('3', 'project.update', {
      project_id: project.project_id,
      folder: null,
    });
    expect(cleared.folder).toBeNull();
  });

  it('approval.list is empty in echo mode — the echo denies fail-closed', async () => {
    const approvals = await t.request<{ approvals: unknown[] }>('1', 'approval.list', {});
    expect(approvals.approvals).toEqual([]);
  });
});
