/** Fallback offline mock implementations for episodic.* methods. */

import type {
  ConsolidatedPersona,
  EpisodeRecord,
  EpisodicTurn,
  HierarchyStatsResult,
  TemporalEntityFact,
} from './episodic-kg';

let mockWorkingTurns = 4;
let mockEpisodesCount = 3;
let mockFactsCount = 5;

export function resetEchoEpisodic() {
  mockWorkingTurns = 0;
  mockEpisodesCount = 0;
  mockFactsCount = 0;
}

export function echoEpisodicRecordEvent(
  _sessionId = 'default_session',
  speaker = 'user',
  text = '',
  sentiment = 0.0,
  metadata?: Record<string, unknown>,
): { status: string; turn: EpisodicTurn } {
  mockWorkingTurns += 1;
  return {
    status: 'recorded',
    turn: {
      turn_id: `turn-${Math.random().toString(16).slice(2, 8)}`,
      speaker,
      text: text || 'رویداد تعاملی ثبت‌شده در بافر حافظه کاری',
      tokens: Math.max(8, text.split(' ').length * 2),
      sentiment,
      timestamp: Date.now() / 1000,
      metadata,
    },
  };
}

export function echoEpisodicCompressSession(
  sessionId = 'default_session',
  _turns?: Array<Record<string, unknown>>,
  domain = 'general',
): { status: string; episode: EpisodeRecord } {
  mockEpisodesCount += 1;
  const jNow = '1403/06/25';
  return {
    status: 'compressed',
    episode: {
      episode_id: `ep-${Math.random().toString(16).slice(2, 8)}`,
      session_id: sessionId,
      title_fa: `نشست اپیزودیک در حوزه ${domain}`,
      title_en: `Episodic Session in ${domain}`,
      summary_fa: `فشرده‌سازی نشست ${sessionId} با استخراج اهداف و دستاوردهای کلیدی در تاریخ ${jNow}.`,
      goals: [`تحلیل جامع مسائل حوزه ${domain}`, 'بهینه‌سازی جریان کاری'],
      outcomes: ['استخراج بینش‌های پایدار', 'ثبت در گراف دانش زمانی'],
      milestones: ['شروع گفتگو', 'طرح مسئله', 'نتیجه‌گیری و سنتز نهایی'],
      sentiment_score: 0.65,
      importance_score: 4,
      started_at: Date.now() / 1000 - 300,
      ended_at: Date.now() / 1000,
      jalali_date: jNow,
      linked_entities: [domain, sessionId, 'DreamV3.2'],
    },
  };
}

export function echoEpisodicQueryTimeline(
  query = '',
  _startJalali = '',
  _endJalali = '',
  _minImportance = 1,
  limit = 20,
): { status: string; count: number; episodes: EpisodeRecord[] } {
  const episodes: EpisodeRecord[] = [
    {
      episode_id: 'ep-001',
      session_id: 'sess_arch_v3',
      title_fa: 'طراحی معماری حافظه سلسله‌مراتبی دریم',
      title_en: 'Hierarchical Memory Architecture Design',
      summary_fa: 'بررسی و پیاده‌سازی ۴ سطح حافظه (Working, Episodic, Temporal KG, Persona).',
      goals: ['رسیدن به دقت شناختی بالا', 'کاهش هدررفت توکن کانتکست'],
      outcomes: ['پیاده‌سازی موفق موتور حافظه', 'پاس شدن تمام تست‌های اعتبارسنجی'],
      milestones: ['تعریف پروتکل', 'پیاده‌سازی موتور پایتون', 'تست فرانت‌اند'],
      sentiment_score: 0.85,
      importance_score: 5,
      started_at: Date.now() / 1000 - 3600 * 24,
      ended_at: Date.now() / 1000 - 3600 * 23,
      jalali_date: '1403/06/24',
      linked_entities: ['معماری_سیستم', 'حافظه_بلندمدت', 'گراف_دانش'],
    },
    {
      episode_id: 'ep-002',
      session_id: 'sess_vision_studio',
      title_fa: 'راه‌اندازی استودیوی بینایی و ردگیری المان‌های صفحه',
      title_en: 'Vision & Screen Grounding Studio Launch',
      summary_fa: 'پیاده‌سازی رابط کاربری تعاملی برای ادراک بصری و گراف‌های Mermaid/SVG.',
      goals: ['ردگیری اهداف کلیک', 'تجزیه جریان ویدیویی'],
      outcomes: ['اتصال کامل کلاینت و بریج پایتون'],
      milestones: ['طراحی بوم بصری', 'تست دسترس‌پذیری صفر خطای Axe'],
      sentiment_score: 0.75,
      importance_score: 4,
      started_at: Date.now() / 1000 - 3600 * 48,
      ended_at: Date.now() / 1000 - 3600 * 47,
      jalali_date: '1403/06/23',
      linked_entities: ['بینایی_ماشین', 'استودیو_دسکتاپ'],
    },
  ];

  const filtered = query
    ? episodes.filter(
        (e) =>
          e.title_fa.includes(query) ||
          e.summary_fa.includes(query) ||
          e.linked_entities.some((k) => k.includes(query)),
      )
    : episodes;

  return {
    status: 'ok',
    count: filtered.length,
    episodes: filtered.slice(0, limit),
  };
}

export function echoEpisodicLinkEntityFact(
  episodeId: string,
  entityName: string,
  entityType = 'concept',
  relationType = 'references',
  targetEntity = 'DreamAgent',
  jalaliDate = '1403/06/25',
): { status: string; fact: TemporalEntityFact } {
  mockFactsCount += 1;
  return {
    status: 'linked',
    fact: {
      fact_id: `fact-${Math.random().toString(16).slice(2, 8)}`,
      episode_id: episodeId,
      entity_name: entityName,
      entity_type: entityType,
      relation: relationType,
      target_name: targetEntity,
      valid_from_jalali: jalaliDate,
      confidence: 0.98,
      timestamp: Date.now() / 1000,
    },
  };
}

export function echoEpisodicConsolidate(
  _forceDecay = false,
  _minEpisodes = 1,
): { status: string; persona: ConsolidatedPersona } {
  return {
    status: 'consolidated',
    persona: {
      profile_id: 'persona_distilled',
      user_title_fa: 'کاربر ارشد و توسعه‌دهنده اصلی دریم',
      primary_domains: ['مهندسی هوش مصنوعی', 'معماری سیستم‌های توزیع‌شده', 'گراف دانش زمانی'],
      key_preferences: {
        language: 'fa',
        tone: 'professional_engineering',
        precision: 'extreme',
      },
      skill_masteries: {
        ai_agents: 0.98,
        system_architecture: 0.96,
        fullstack_typescript: 0.94,
        python_backend: 0.97,
      },
      recurring_goals: [
        'توسعه عامل هوشمند دریم با قابلیت‌های فراتر از نمونه‌های مرجع',
        'ایجاد یکپارچگی پایدار در تمام پلتفرم‌ها',
      ],
      consolidated_at: Date.now() / 1000,
      total_episodes_synthesized: mockEpisodesCount,
    },
  };
}

export function echoEpisodicGetHierarchyStats(): HierarchyStatsResult {
  return {
    uptime_sec: 128.45,
    total_operations: mockWorkingTurns + mockEpisodesCount + mockFactsCount,
    tier_0_working_turns: mockWorkingTurns,
    tier_1_episodes_count: mockEpisodesCount,
    tier_2_temporal_facts_count: mockFactsCount,
    tier_3_persona_domains: 4,
    total_knowledge_graph_nodes: 18,
    total_knowledge_graph_edges: 24,
    compression_ratio: 3.5,
    status: 'healthy',
  };
}

export function echoEpisodicReset() {
  resetEchoEpisodic();
  return { status: 'reset', tier_0_working_turns: 0, tier_1_episodes_count: 0 };
}
