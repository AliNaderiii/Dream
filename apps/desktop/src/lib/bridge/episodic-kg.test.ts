/** Vitest suite for episodic-kg bridge client wrappers and echo offline fallback. */

import { beforeEach, describe, expect, it } from 'vitest';
import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
import { resetEchoEpisodic } from './echo-episodic-kg';
import {
  episodicCompressSession,
  episodicConsolidate,
  episodicGetHierarchyStats,
  episodicLinkEntityFact,
  episodicQueryTimeline,
  episodicRecordEvent,
  episodicReset,
} from './episodic-kg';

describe('Episodic Memory & Temporal KG Bridge Client', () => {
  let client: BridgeClient;

  beforeEach(async () => {
    resetBridgeClient();
    resetEchoEpisodic();
    client = getBridgeClient();
    await episodicReset(client);
  });

  it('records working turns into Tier 0 buffer', async () => {
    const res = await episodicRecordEvent(client, 'test_sess', 'user', 'تست ثبت رویداد کاری', 0.8);
    expect(res.status).toBe('recorded');
    expect(res.turn.speaker).toBe('user');
    expect(res.turn.sentiment).toBe(0.8);
  });

  it('compresses working turns into Tier 1 episode', async () => {
    const res = await episodicCompressSession(client, 'test_sess', undefined, 'ai_agents');
    expect(res.status).toBe('compressed');
    expect(res.episode.title_fa).toContain('ai_agents');
    expect(res.episode.importance_score).toBeGreaterThanOrEqual(3);
  });

  it('queries temporal timeline with filters', async () => {
    await episodicCompressSession(client, 'sess_1', undefined, 'architecture');
    const res = await episodicQueryTimeline(client, 'معماری');
    expect(res.status).toBe('ok');
    expect(res.episodes.length).toBeGreaterThanOrEqual(1);
  });

  it('links episodic entity facts to temporal KG', async () => {
    const factRes = await episodicLinkEntityFact(
      client,
      'ep-001',
      'EpisodicMemoryEngine',
      'concept',
      'references',
      'DreamAgent',
      '1403/06/25',
    );
    expect(factRes.status).toBe('linked');
    expect(factRes.fact.entity_name).toBe('EpisodicMemoryEngine');
    expect(factRes.fact.valid_from_jalali).toBe('1403/06/25');
  });

  it('consolidates Tier 3 persona and gets stats', async () => {
    const personaRes = await episodicConsolidate(client, false, 1);
    expect(personaRes.status).toBe('consolidated');
    expect(personaRes.persona.primary_domains.length).toBeGreaterThanOrEqual(1);

    const stats = await episodicGetHierarchyStats(client);
    expect(stats.status).toBe('healthy');
    expect(stats.tier_3_persona_domains).toBeGreaterThanOrEqual(1);
  });
});
