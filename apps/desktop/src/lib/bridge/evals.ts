/**
 * Typed client wrappers for Evals, Self-Evolution, DPO Distillation & Hermes Benchmark RPC.
 */

import type { BridgeClient } from './client';
import * as echo from './echo-evals';

export interface EvalCaseResult {
  case_id: string;
  category: string;
  passed: boolean;
  score: number;
  actual_response: string;
  actual_tools_called: string[];
  latency_ms: number;
  tokens_consumed: number;
  feedback_fa: string;
  timestamp: number;
}

export interface BenchmarkReport {
  run_id: string;
  suite_id: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  overall_pass_rate: number;
  overall_composite_score: number;
  category_scores: Record<string, number>;
  average_latency_ms: number;
  total_tokens_consumed: number;
  results: EvalCaseResult[];
  summary_fa: string;
  duration_ms: number;
  timestamp: number;
}

export interface EvalSuiteInfo {
  suite_id: string;
  name: string;
  description_fa: string;
  total_cases: number;
  target_pass_rate: number;
}

export interface ComparisonDimension {
  id: string;
  name_en: string;
  name_fa: string;
  dream_score: number;
  hermes_score: number;
  openclaw_score: number;
  delta_vs_hermes: string;
  winner: string;
  details_fa: string;
}

export interface HermesComparisonReport {
  status: string;
  benchmark_name: string;
  timestamp: number;
  overall_winner: string;
  dream_composite_score: number;
  hermes_composite_score: number;
  openclaw_composite_score: number;
  win_rate_percentage: number;
  dimensions: ComparisonDimension[];
  verdict_fa: string;
}

export interface DpoPair {
  pair_id: string;
  prompt: string;
  chosen: string;
  rejected: string;
  reward_delta: number;
  category: string;
}

export interface StrategyGeneInfo {
  gene_id: string;
  name: string;
  description_fa: string;
  prompt_template: string;
  heuristics: string[];
  preferred_tools: string[];
  fitness_score: number;
  elo_rating: number;
  generation: number;
  wins: number;
  losses: number;
  matches_played: number;
}

export interface EvolutionStatusResponse {
  status: string;
  total_strategies: number;
  leaderboard: StrategyGeneInfo[];
  top_strategy: StrategyGeneInfo | null;
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

export function evalsListSuites(
  client: BridgeClient,
): Promise<{ status: string; suites: EvalSuiteInfo[]; total_suites: number }> {
  return echoOr(client, () => echo.echoEvalsListSuites(), 'evals.list_suites', {});
}

export function evalsRunSuite(
  client: BridgeClient,
  suite_id: string,
): Promise<{ status: string; report: BenchmarkReport }> {
  return echoOr(client, () => echo.echoEvalsRunSuite(suite_id), 'evals.run_suite', { suite_id });
}

export function evalsCompareHermes(client: BridgeClient): Promise<HermesComparisonReport> {
  return echoOr(client, () => echo.echoEvalsCompareHermes(), 'evals.compare_hermes', {});
}

export function evalsDistillDpo(
  client: BridgeClient,
  count = 3,
): Promise<{ status: string; total_pairs: number; pairs: DpoPair[]; export_format: string }> {
  return echoOr(client, () => echo.echoEvalsDistillDpo(count), 'evals.distill_dpo', { count });
}

export function evalsEvolveGeneration(
  client: BridgeClient,
  rounds = 2,
): Promise<{
  status: string;
  rounds_executed: number;
  mutated_gene: StrategyGeneInfo | null;
  leaderboard: StrategyGeneInfo[];
  top_strategy: StrategyGeneInfo | null;
}> {
  return echoOr(client, () => echo.echoEvalsEvolveGeneration(rounds), 'evals.evolve_generation', {
    rounds,
  });
}

export function evalsGetEvolutionStatus(client: BridgeClient): Promise<EvolutionStatusResponse> {
  return echoOr(client, () => echo.echoEvalsGetEvolutionStatus(), 'evals.get_evolution_status', {});
}

export function evalsReset(client: BridgeClient): Promise<{ status: string }> {
  return echoOr(client, () => echo.echoEvalsReset(), 'evals.reset', {});
}
