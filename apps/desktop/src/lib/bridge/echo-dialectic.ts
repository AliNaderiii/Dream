/** Fallback offline mock implementations for dialectic.* methods. */

import type {
  BeliefNode,
  DialecticDebateResult,
  DialecticMemorySnapshot,
  DialecticRelation,
  DialecticTension,
} from './dialectic';

let mockBeliefs: BeliefNode[] = [
  {
    belief_id: 'b_001',
    domain: 'architecture',
    statement: 'Monolithic architectures simplify operational deployment and observability',
    confidence: 0.88,
    status: 'nuanced',
    evidence: ['System benchmark v3.0'],
    created_at: Date.now() - 3600000,
    updated_at: Date.now() - 3600000,
  },
  {
    belief_id: 'b_002',
    domain: 'architecture',
    statement: 'Microservices allow fine-grained scaling for independent teams',
    confidence: 0.82,
    status: 'nuanced',
    evidence: ['Engineering org study'],
    created_at: Date.now() - 3000000,
    updated_at: Date.now() - 3000000,
  },
  {
    belief_id: 'b_003',
    domain: 'architecture',
    statement:
      'Modular monolith with strict interface boundaries balances simplicity and scalability',
    confidence: 0.96,
    status: 'active',
    evidence: ['Reconciled from tension t_001'],
    created_at: Date.now() - 1000000,
    updated_at: Date.now() - 1000000,
  },
];

let mockRelations: DialecticRelation[] = [
  {
    relation_id: 'r_001',
    source_id: 'b_001',
    target_id: 'b_003',
    relation_type: 'refines',
    notes: 'Synthesized into modular monolith',
  },
  {
    relation_id: 'r_002',
    source_id: 'b_002',
    target_id: 'b_003',
    relation_type: 'refines',
    notes: 'Synthesized into modular monolith',
  },
];

let mockTensions: DialecticTension[] = [
  {
    tension_id: 't_001',
    belief_ids: ['b_001', 'b_002'],
    description: 'Contradiction between Monolith and Microservices approach',
    detected_at: Date.now() - 2000000,
    resolved: true,
    resolution_notes: 'Modular monolith with strict interface boundaries',
  },
];

export function resetEchoDialectic() {
  mockBeliefs = [];
  mockRelations = [];
  mockTensions = [];
}

export function echoDialecticObserve(statement: string, domain = 'general') {
  const existing = mockBeliefs.find(
    (b) => b.statement.toLowerCase() === statement.toLowerCase() && b.domain === domain,
  );
  if (existing) {
    existing.confidence = Math.min(1.0, existing.confidence + 0.1);
    existing.updated_at = Date.now();
    return { status: 'observed', belief: existing };
  }
  const belief: BeliefNode = {
    belief_id: `b_${Math.random().toString(16).slice(2, 8)}`,
    domain,
    statement,
    confidence: 0.85,
    status: 'active',
    evidence: ['Observed conversational turn'],
    created_at: Date.now(),
    updated_at: Date.now(),
  };
  mockBeliefs.push(belief);
  return { status: 'observed', belief };
}

export function echoDialecticAddBelief(
  statement: string,
  domain = 'general',
  confidence = 0.8,
  evidence: string[] = [],
) {
  const belief: BeliefNode = {
    belief_id: `b_${Math.random().toString(16).slice(2, 8)}`,
    domain,
    statement,
    confidence,
    status: 'active',
    evidence,
    created_at: Date.now(),
    updated_at: Date.now(),
  };
  mockBeliefs.push(belief);
  return { status: 'added', belief };
}

export function echoDialecticLinkBeliefs(
  sourceId: string,
  targetId: string,
  relationType: 'supports' | 'contradicts' | 'refines' | 'originates_from' | 'causes' = 'supports',
  notes = '',
) {
  const relation: DialecticRelation = {
    relation_id: `r_${Math.random().toString(16).slice(2, 8)}`,
    source_id: sourceId,
    target_id: targetId,
    relation_type: relationType,
    notes,
  };
  mockRelations.push(relation);

  if (relationType === 'contradicts') {
    const tension: DialecticTension = {
      tension_id: `t_${sourceId}_${targetId}`,
      belief_ids: [sourceId, targetId],
      description: `Contradiction between ${sourceId} and ${targetId}`,
      detected_at: Date.now(),
      resolved: false,
    };
    mockTensions.push(tension);
  }

  return { status: 'linked', relation };
}

export function echoDialecticDetectTensions() {
  return {
    status: 'ok',
    tensions: [...mockTensions],
    count: mockTensions.length,
  };
}

export function echoDialecticReconcileTension(tensionId: string, nuancedStatement: string) {
  const tension = mockTensions.find((t) => t.tension_id === tensionId);
  if (tension) {
    tension.resolved = true;
    tension.resolution_notes = nuancedStatement;
  }

  const nuancedBelief: BeliefNode = {
    belief_id: `b_${Math.random().toString(16).slice(2, 8)}`,
    domain: 'synthesized',
    statement: nuancedStatement,
    confidence: 0.95,
    status: 'active',
    evidence: [`Reconciled from tension ${tensionId}`],
    created_at: Date.now(),
    updated_at: Date.now(),
  };
  mockBeliefs.push(nuancedBelief);

  return {
    status: 'reconciled',
    nuanced_belief: nuancedBelief,
  };
}

export function echoDialecticQuery(query: string, limit = 5) {
  const q = query.toLowerCase();
  const matched = mockBeliefs.filter(
    (b) => b.statement.toLowerCase().includes(q) || b.domain.toLowerCase().includes(q),
  );
  return {
    status: 'ok',
    beliefs: matched.slice(0, limit),
    count: matched.length,
  };
}

export function echoDialecticSnapshot(): DialecticMemorySnapshot {
  const unresolved = mockTensions.filter((t) => !t.resolved).length;
  const summary = mockBeliefs
    .map((b) => `- [${b.domain}] ${b.statement} (conf: ${b.confidence.toFixed(2)})`)
    .join('\n');

  return {
    nodes_count: mockBeliefs.length,
    tensions_count: mockTensions.length,
    unresolved_tensions: unresolved,
    top_beliefs: [...mockBeliefs],
    beliefs: [...mockBeliefs],
    synthesized_summary: summary || 'No active beliefs recorded.',
    timestamp: Date.now(),
  };
}

export function echoDialecticDebateTurn(topic: string, domain = 'general'): DialecticDebateResult {
  const thesis: BeliefNode = {
    belief_id: `b_th_${Math.random().toString(16).slice(2, 6)}`,
    domain,
    statement: `پروپوزال اولیه (Thesis): رویکرد ${topic} بهترین عملکرد و بازدهی را فراهم می‌کند.`,
    confidence: 0.85,
    status: 'active',
    evidence: ['Thesis Agent Proposition'],
    created_at: Date.now(),
    updated_at: Date.now(),
  };

  const antithesis: BeliefNode = {
    belief_id: `b_at_${Math.random().toString(16).slice(2, 6)}`,
    domain,
    statement: `نقد و چالش (Antithesis): ریسک‌های وابستگی و پیچیدگی‌های استقرار در فرضیه ${topic} نیازمند بازبینی است.`,
    confidence: 0.8,
    status: 'contradicted',
    evidence: ['Antithesis Agent Critical Review'],
    created_at: Date.now(),
    updated_at: Date.now(),
  };

  const synthesis: BeliefNode = {
    belief_id: `b_syn_${Math.random().toString(16).slice(2, 6)}`,
    domain,
    statement: `سنتز نهایی (Synthesis): بهره‌گیری از توانمندی‌های ${topic} با مدیریت متمرکز ریسک‌ها و اعتبارسنجی مداوم.`,
    confidence: 0.95,
    status: 'active',
    evidence: [`Synthesized from ${thesis.belief_id} and ${antithesis.belief_id}`],
    created_at: Date.now(),
    updated_at: Date.now(),
  };

  mockBeliefs.push(thesis, antithesis, synthesis);
  mockRelations.push(
    {
      relation_id: `r_${Math.random().toString(16).slice(2, 6)}`,
      source_id: antithesis.belief_id,
      target_id: thesis.belief_id,
      relation_type: 'contradicts',
      notes: 'Antithesis challenge',
    },
    {
      relation_id: `r_${Math.random().toString(16).slice(2, 6)}`,
      source_id: thesis.belief_id,
      target_id: synthesis.belief_id,
      relation_type: 'refines',
      notes: 'Integrated into synthesis',
    },
  );

  return {
    status: 'completed',
    topic,
    domain,
    thesis,
    antithesis,
    synthesis,
    graph_snapshot: echoDialecticSnapshot(),
  };
}

export function echoDialecticReset() {
  resetEchoDialectic();
  return { status: 'reset', nodes_count: 0 };
}
