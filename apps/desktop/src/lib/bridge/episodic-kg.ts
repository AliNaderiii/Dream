/** Typed client wrappers for episodic.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-episodic-kg';

export interface EpisodicTurn {
  turn_id: string;
  speaker: string;
  text: string;
  tokens: number;
  sentiment: number;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface EpisodeRecord {
  episode_id: string;
  session_id: string;
  title_fa: string;
  title_en: string;
  summary_fa: string;
  goals: string[];
  outcomes: string[];
  milestones: string[];
  sentiment_score: number;
  importance_score: number;
  started_at: number;
  ended_at: number;
  jalali_date: string;
  linked_entities: string[];
  metadata?: Record<string, unknown>;
}

export interface TemporalEntityFact {
  fact_id: string;
  episode_id: string;
  entity_name: string;
  entity_type: string;
  relation: string;
  target_name: string;
  valid_from_jalali: string;
  valid_to_jalali?: string | null;
  confidence: number;
  timestamp: number;
}

export interface ConsolidatedPersona {
  profile_id: string;
  user_title_fa: string;
  primary_domains: string[];
  key_preferences: Record<string, unknown>;
  skill_masteries: Record<string, number>;
  recurring_goals: string[];
  consolidated_at: number;
  total_episodes_synthesized: number;
}

export interface HierarchyStatsResult {
  uptime_sec: number;
  total_operations: number;
  tier_0_working_turns: number;
  tier_1_episodes_count: number;
  tier_2_temporal_facts_count: number;
  tier_3_persona_domains: number;
  total_knowledge_graph_nodes: number;
  total_knowledge_graph_edges: number;
  compression_ratio: number;
  status: string;
}

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function episodicRecordEvent(
  client: BridgeClient,
  sessionId = 'default_session',
  speaker = 'user',
  text = '',
  sentiment = 0.0,
  metadata?: Record<string, unknown>,
): Promise<{ status: string; turn: EpisodicTurn }> {
  return echoOr(
    client,
    () => echo.echoEpisodicRecordEvent(sessionId, speaker, text, sentiment, metadata),
    'episodic.record_event',
    { session_id: sessionId, speaker, text, sentiment, metadata },
  );
}

export function episodicCompressSession(
  client: BridgeClient,
  sessionId = 'default_session',
  turns?: Array<Record<string, unknown>>,
  domain = 'general',
): Promise<{ status: string; episode: EpisodeRecord }> {
  return echoOr(
    client,
    () => echo.echoEpisodicCompressSession(sessionId, turns, domain),
    'episodic.compress_session',
    { session_id: sessionId, turns, domain },
  );
}

export function episodicQueryTimeline(
  client: BridgeClient,
  query = '',
  startJalali = '',
  endJalali = '',
  minImportance = 1,
  limit = 20,
): Promise<{ status: string; count: number; episodes: EpisodeRecord[] }> {
  return echoOr(
    client,
    () => echo.echoEpisodicQueryTimeline(query, startJalali, endJalali, minImportance, limit),
    'episodic.query_timeline',
    {
      query,
      start_jalali: startJalali,
      end_jalali: endJalali,
      min_importance: minImportance,
      limit,
    },
  );
}

export function episodicLinkEntityFact(
  client: BridgeClient,
  episodeId: string,
  entityName: string,
  entityType = 'concept',
  relationType = 'references',
  targetEntity = 'DreamAgent',
  jalaliDate?: string,
): Promise<{ status: string; fact: TemporalEntityFact }> {
  return echoOr(
    client,
    () =>
      echo.echoEpisodicLinkEntityFact(
        episodeId,
        entityName,
        entityType,
        relationType,
        targetEntity,
        jalaliDate,
      ),
    'episodic.link_entity_fact',
    {
      episode_id: episodeId,
      entity_name: entityName,
      entity_type: entityType,
      relation_type: relationType,
      target_entity: targetEntity,
      jalali_date: jalaliDate,
    },
  );
}

export function episodicConsolidate(
  client: BridgeClient,
  forceDecay = false,
  minEpisodes = 1,
): Promise<{ status: string; persona: ConsolidatedPersona }> {
  return echoOr(
    client,
    () => echo.echoEpisodicConsolidate(forceDecay, minEpisodes),
    'episodic.consolidate',
    { force_decay: forceDecay, min_episodes: minEpisodes },
  );
}

export function episodicGetHierarchyStats(client: BridgeClient): Promise<HierarchyStatsResult> {
  return echoOr(client, () => echo.echoEpisodicGetHierarchyStats(), 'episodic.get_hierarchy_stats', {});
}

export function episodicReset(
  client: BridgeClient,
): Promise<{ status: string; tier_0_working_turns: number; tier_1_episodes_count: number }> {
  return echoOr(client, () => echo.echoEpisodicReset(), 'episodic.reset', {});
}
