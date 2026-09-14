/** Typed client wrappers for dialectic.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-dialectic';

export interface BeliefNode {
  belief_id: string;
  domain: string;
  statement: string;
  confidence: number;
  status: 'active' | 'contradicted' | 'superseded' | 'nuanced';
  evidence: string[];
  created_at: number;
  updated_at: number;
}

export interface DialecticRelation {
  relation_id: string;
  source_id: string;
  target_id: string;
  relation_type: 'supports' | 'contradicts' | 'refines' | 'originates_from' | 'causes';
  notes?: string;
}

export interface DialecticTension {
  tension_id: string;
  belief_ids: string[];
  description: string;
  detected_at: number;
  resolved: boolean;
  resolution_notes?: string;
}

export interface DialecticMemorySnapshot {
  nodes_count: number;
  tensions_count: number;
  unresolved_tensions: number;
  top_beliefs: BeliefNode[];
  beliefs?: BeliefNode[];
  synthesized_summary: string;
  timestamp: number;
}

export interface DialecticDebateResult {
  status: string;
  topic: string;
  domain: string;
  thesis: BeliefNode;
  antithesis: BeliefNode;
  synthesis: BeliefNode;
  graph_snapshot: DialecticMemorySnapshot;
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

export function dialecticObserve(
  client: BridgeClient,
  statement: string,
  domain = 'general',
): Promise<{ status: string; belief: BeliefNode }> {
  return echoOr(client, () => echo.echoDialecticObserve(statement, domain), 'dialectic.observe', {
    statement,
    domain,
  });
}

export function dialecticAddBelief(
  client: BridgeClient,
  statement: string,
  domain = 'general',
  confidence = 0.8,
  evidence: string[] = [],
): Promise<{ status: string; belief: BeliefNode }> {
  return echoOr(
    client,
    () => echo.echoDialecticAddBelief(statement, domain, confidence, evidence),
    'dialectic.add_belief',
    { statement, domain, confidence, evidence },
  );
}

export function dialecticLinkBeliefs(
  client: BridgeClient,
  sourceId: string,
  targetId: string,
  relationType: 'supports' | 'contradicts' | 'refines' | 'originates_from' | 'causes' = 'supports',
  notes = '',
): Promise<{ status: string; relation: DialecticRelation }> {
  return echoOr(
    client,
    () => echo.echoDialecticLinkBeliefs(sourceId, targetId, relationType, notes),
    'dialectic.link_beliefs',
    { source_id: sourceId, target_id: targetId, relation_type: relationType, notes },
  );
}

export function dialecticDetectTensions(
  client: BridgeClient,
): Promise<{ status: string; tensions: DialecticTension[]; count: number }> {
  return echoOr(client, () => echo.echoDialecticDetectTensions(), 'dialectic.detect_tensions', {});
}

export function dialecticReconcileTension(
  client: BridgeClient,
  tensionId: string,
  nuancedStatement: string,
): Promise<{ status: string; nuanced_belief: BeliefNode }> {
  return echoOr(
    client,
    () => echo.echoDialecticReconcileTension(tensionId, nuancedStatement),
    'dialectic.reconcile_tension',
    { tension_id: tensionId, nuanced_statement: nuancedStatement },
  );
}

export function dialecticQuery(
  client: BridgeClient,
  query: string,
  limit = 5,
): Promise<{ status: string; beliefs: BeliefNode[]; count: number }> {
  return echoOr(client, () => echo.echoDialecticQuery(query, limit), 'dialectic.query', {
    query,
    limit,
  });
}

export function dialecticSnapshot(client: BridgeClient): Promise<DialecticMemorySnapshot> {
  return echoOr(client, () => echo.echoDialecticSnapshot(), 'dialectic.snapshot', {});
}

export function dialecticDebateTurn(
  client: BridgeClient,
  topic: string,
  domain = 'general',
): Promise<DialecticDebateResult> {
  return echoOr(
    client,
    () => echo.echoDialecticDebateTurn(topic, domain),
    'dialectic.debate_turn',
    { topic, domain },
  );
}

export function dialecticReset(
  client: BridgeClient,
): Promise<{ status: string; nodes_count: number }> {
  return echoOr(client, () => echo.echoDialecticReset(), 'dialectic.reset', {});
}
