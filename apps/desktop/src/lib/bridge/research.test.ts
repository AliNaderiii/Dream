/**
 * Unit tests for the research bridge wrapper (P2).
 */

import { describe, expect, it } from 'vitest';

import {
  redactSecrets,
  validateResearchCreate,
  validateResearchPlan,
  mapResearchError,
} from './research';
import type { ResearchCreateParams, ResearchPlan } from './research-types';

describe('research bridge', () => {
  describe('validateResearchCreate', () => {
    it('accepts valid params', () => {
      const params: ResearchCreateParams = {
        topic: 'Customer churn analysis',
        objective: 'Identify the main causes of customer churn',
        depth: 'deep',
        data_sources: [],
      };
      expect(validateResearchCreate(params)).toBeNull();
    });

    it('rejects empty topic', () => {
      const params: ResearchCreateParams = {
        topic: '',
        objective: 'Test',
        depth: 'simple',
        data_sources: [],
      };
      expect(validateResearchCreate(params)).toContain('Topic');
    });

    it('rejects empty objective', () => {
      const params: ResearchCreateParams = {
        topic: 'Test',
        objective: '',
        depth: 'simple',
        data_sources: [],
      };
      expect(validateResearchCreate(params)).toContain('Objective');
    });

    it('rejects invalid depth', () => {
      const params: ResearchCreateParams = {
        topic: 'Test',
        objective: 'Test',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        depth: 'invalid' as any as ResearchCreateParams['depth'],
        data_sources: [],
      };
      expect(validateResearchCreate(params)).toContain('Depth');
    });

    it('rejects topic > 500 chars', () => {
      const params: ResearchCreateParams = {
        topic: 'a'.repeat(501),
        objective: 'Test',
        depth: 'simple',
        data_sources: [],
      };
      expect(validateResearchCreate(params)).toContain('500');
    });
  });

  describe('validateResearchPlan', () => {
    it('accepts valid plan', () => {
      const plan: ResearchPlan = {
        research_questions: ['Q1', 'Q2'],
        hypotheses: ['H1'],
        methodology: 'Mixed methods',
        outline: [{ title: 'Intro' }],
      };
      expect(validateResearchPlan(plan)).toBeNull();
    });

    it('rejects empty questions', () => {
      const plan: ResearchPlan = {
        research_questions: [],
        hypotheses: ['H1'],
        methodology: 'Test',
        outline: [{ title: 'Intro' }],
      };
      expect(validateResearchPlan(plan)).toContain('research question');
    });

    it('rejects empty outline', () => {
      const plan: ResearchPlan = {
        research_questions: ['Q1'],
        hypotheses: ['H1'],
        methodology: 'Test',
        outline: [],
      };
      expect(validateResearchPlan(plan)).toContain('outline');
    });
  });

  describe('redactSecrets', () => {
    it('redacts OpenAI-style keys', () => {
      const text = 'Using key sk-1234567890abcdef1234567890abcdef';
      expect(redactSecrets(text)).toContain('[REDACTED]');
      expect(redactSecrets(text)).not.toContain('sk-');
    });

    it('redacts GitHub tokens', () => {
      const text = 'Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz';
      expect(redactSecrets(text)).toContain('[REDACTED]');
      expect(redactSecrets(text)).not.toContain('ghp_');
    });

    it('redacts AWS keys', () => {
      const text = 'AKIAIOSFODNN7EXAMPLE';
      expect(redactSecrets(text)).toContain('[REDACTED]');
      expect(redactSecrets(text)).not.toContain('AKIA');
    });

    it('leaves safe text untouched', () => {
      const text = 'This is a normal sentence with no secrets.';
      expect(redactSecrets(text)).toBe(text);
    });
  });

  describe('mapResearchError', () => {
    it('maps session not found', () => {
      const result = mapResearchError(new Error('research session not found: xyz'));
      expect(result.key).toBe('errors.sessionNotFound');
    });

    it('maps no report', () => {
      const result = mapResearchError(new Error('no report for session abc'));
      expect(result.key).toBe('errors.noReport');
    });

    it('maps cancelled', () => {
      const result = mapResearchError(new Error('cancelled'));
      expect(result.key).toBe('errors.cancelled');
    });

    it('maps timed out', () => {
      const result = mapResearchError(new Error('research.stream_progress timed out'));
      expect(result.key).toBe('errors.timedOut');
    });

    it('maps no data sources', () => {
      const result = mapResearchError(new Error('No data sources attached'));
      expect(result.key).toBe('errors.noDataSources');
    });

    it('falls back to unknown', () => {
      const result = mapResearchError(new Error('something weird'));
      expect(result.key).toBe('errors.unknown');
    });
  });
});
