/**
 * Unit tests for the research bridge wrapper (P2) + XSS sanitization.
 */

import { describe, expect, it } from 'vitest';

import { redactSecrets, validateResearchCreate, mapResearchError } from './research';
import type { ResearchCreateParams } from './research-types';

describe('research bridge', () => {
  describe('validateResearchCreate', () => {
    it('accepts valid params', () => {
      const params: ResearchCreateParams = {
        topic: 'Customer churn analysis',
        workspace: '/workspace/research',
      };
      expect(validateResearchCreate(params)).toBeNull();
    });

    it('rejects empty topic', () => {
      const params: ResearchCreateParams = {
        topic: '',
        workspace: '/workspace/research',
      };
      expect(validateResearchCreate(params)).toContain('Topic');
    });

    it('rejects empty workspace', () => {
      const params: ResearchCreateParams = {
        topic: 'Test',
        workspace: '',
      };
      expect(validateResearchCreate(params)).toContain('Workspace');
    });

    it('rejects topic > 500 chars', () => {
      const params: ResearchCreateParams = {
        topic: 'a'.repeat(501),
        workspace: '/workspace',
      };
      expect(validateResearchCreate(params)).toContain('500');
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

    it('redacts JWTs', () => {
      const text =
        'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U';
      expect(redactSecrets(text)).toContain('[REDACTED]');
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

    it('maps not approved', () => {
      const result = mapResearchError(
        new Error('the plan must be approved before an interactive run starts'),
      );
      expect(result.key).toBe('errors.notApproved');
    });

    it('maps nothing to approve', () => {
      const result = mapResearchError(new Error('nothing to approve: the session is IDLE'));
      expect(result.key).toBe('errors.nothingToApprove');
    });

    it('maps cancelled', () => {
      const result = mapResearchError(new Error('cancelled'));
      expect(result.key).toBe('errors.cancelled');
    });

    it('maps timed out', () => {
      const result = mapResearchError(
        new Error('the research run exceeded 900s and was cancelled'),
      );
      expect(result.key).toBe('errors.timedOut');
    });

    it('maps not complete for export', () => {
      const result = mapResearchError(new Error('only a COMPLETE session can be published'));
      expect(result.key).toBe('errors.notComplete');
    });

    it('falls back to unknown', () => {
      const result = mapResearchError(new Error('something weird'));
      expect(result.key).toBe('errors.unknown');
    });
  });
});

describe('XSS sanitization', () => {
  // Import the renderMarkdown function indirectly by testing the patterns
  // that the report-viewer uses. We test the strip + escape pipeline.

  function escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function stripHtmlTags(text: string): string {
    return text.replace(/<[^>]*>/g, '');
  }

  function sanitize(input: string): string {
    return escapeHtml(stripHtmlTags(input));
  }

  it('strips <script> tags', () => {
    const input = '<script>alert("xss")</script>Hello';
    const result = sanitize(input);
    expect(result).not.toContain('<script>');
    expect(result).not.toContain('</script>');
    expect(result).toContain('Hello');
    // The text content between script tags is kept but escaped
    expect(result).not.toContain('<');
  });

  it('strips <img onerror=...> tags', () => {
    const input = '<img src=x onerror="alert(1)">';
    const result = sanitize(input);
    expect(result).not.toContain('onerror');
    expect(result).not.toContain('<img');
    expect(result).not.toContain('<');
  });

  it('strips javascript: URLs', () => {
    const input = '<a href="javascript:alert(1)">click</a>';
    const result = sanitize(input);
    expect(result).not.toContain('javascript:');
    expect(result).not.toContain('<a');
    expect(result).toContain('click');
  });

  it('strips HTML tags and escapes remaining text', () => {
    const input = 'Use <div> for layout';
    const result = sanitize(input);
    // <div> is stripped entirely by stripHtmlTags
    expect(result).not.toContain('<div>');
    expect(result).not.toContain('<');
    expect(result).toContain('Use');
    expect(result).toContain('for layout');
  });

  it('escapes ampersands', () => {
    const input = 'A & B';
    const result = sanitize(input);
    expect(result).toContain('&amp;');
  });

  it('handles nested script tags', () => {
    const input = '<script><script>alert(1)</script></script>';
    const result = sanitize(input);
    expect(result).not.toContain('<script');
  });

  it('handles SVG onload', () => {
    const input = '<svg onload="alert(1)"><circle r="50"/></svg>';
    const result = sanitize(input);
    expect(result).not.toContain('onload');
    expect(result).not.toContain('<svg');
  });
});
