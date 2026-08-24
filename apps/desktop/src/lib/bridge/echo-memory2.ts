/**
 * Echo runtime for the `memory2.*` family — the browser/test stand-in for
 * `dream.memory_stores.BoundedMemory`.
 *
 * The rules mirror the kernel exactly, because the desktop panel's laws are
 * pinned against this runtime as much as against the sidecar:
 *
 * - capacity accounting counts the separator between entries;
 * - an overflowing add/replace is *refused* — the store stays byte-identical;
 * - replace/remove resolve a fragment that must match exactly one entry
 *   (normalised through the shared Persian normalizer);
 * - `memory2.status` answers the snapshot frozen when the runtime was built,
 *   so later writes never rewrite it — the frozen-prompt contract.
 *
 * Echo capacities differ from the kernel's profile default on purpose
 * (2,200 notes / 1,200 profile) so a rendered header proves which capacities
 * the panel was actually handed, not a constant baked into the UI.
 */

import { normalizeFa } from '@/lib/schedule/normalize-fa';

import { boundedHeader, boundedUsedChars, BOUNDED_SEPARATOR } from './memory';
import { BridgeRpcError } from './errors';
import type { RpcParams } from './types';

/** Wire shape of one store snapshot (mirrors `memory2.snapshot`). */
export interface EchoBoundedSnapshot {
  target: 'memory' | 'user';
  header: string;
  used_chars: number;
  capacity: number;
  entries: string[];
}

export type EchoBoundedTarget = 'memory' | 'user';

export const ECHO_NOTES_CAPACITY = 2_200;
export const ECHO_PROFILE_CAPACITY = 1_200;

function invalid(message: string): BridgeRpcError {
  return new BridgeRpcError({ code: -32602, message });
}

/** Bilingual refusal for an overflowing write; nothing was truncated. */
function capacityRefusal(target: string, overBy: number, header: string): BridgeRpcError {
  return new BridgeRpcError({
    code: -32602,
    message:
      // Gloss: «افزودن رد شد و چیزی تغییر نکرد؛ فروشگاه پر است.»
      '\u0627\u0641\u0632\u0648\u062f\u0646 \u0631\u062f \u0634\u062f \u0648 \u0686\u06cc\u0632\u06cc \u062a\u063a\u06cc\u06cc\u0631 \u0646\u06a9\u0631\u062f\u061b ' +
      `\u0641\u0631\u0648\u0634\u06af\u0627\u0647 '${target}' \u067e\u0631 \u0627\u0633\u062a (${header}). ` +
      `Add refused and nothing changed: store '${target}' is over capacity by ${overBy} chars; ` +
      'nothing was truncated or stored. Consolidate with remove/replace, then retry.',
  });
}

/** Bilingual refusal when a fragment matches no entry. */
function notFoundRefusal(fragment: string): BridgeRpcError {
  return new BridgeRpcError({
    code: -32602,
    message:
      // Gloss: «هیچ مدخلی این عبارت را نمی‌داشت؛ فروشگاه دست‌نخورده ماند.»
      '\u0647\u06cc\u0686 \u0645\u062f\u062e\u0644\u06cc \u0627\u06cc\u0646 \u0639\u0628\u0627\u0631\u062a \u0631\u0627 \u0646\u0645\u06cc\u200c\u062f\u0627\u0634\u062a\u061b ' +
      '\u0641\u0631\u0648\u0634\u06af\u0627\u0647 \u062f\u0633\u062a\u200c\u0646\u062e\u0648\u0631\u062f\u0647 \u0645\u0627\u0646\u062f. ' +
      `No entry contains '${fragment}'; the store is unchanged. Send a fragment of one entry.`,
  });
}

/** Bilingual refusal when a fragment matches more than one entry. */
function ambiguousRefusal(count: number): BridgeRpcError {
  return new BridgeRpcError({
    code: -32602,
    message:
      // Gloss: «عبارت در چند مدخل پیدا شد؛ عبارتی ممتدتر بفرست.»
      `\u0639\u0628\u0627\u0631\u062a \u062f\u0631 ${count} \u0645\u062f\u062e\u0644 \u067e\u06cc\u062f\u0627 \u0634\u062f\u061b ` +
      '\u0639\u0628\u0627\u0631\u062a\u06cc \u0645\u0645\u062a\u062f\u062a\u0631 \u0628\u0641\u0631\u0633\u062a. ' +
      `Fragment matched ${count} entries; the store is unchanged. Send a longer fragment.`,
  });
}

/** One echo bounded store with kernel-shaped capacity discipline. */
class EchoBoundedStore {
  private entries: string[];

  constructor(
    readonly target: EchoBoundedTarget,
    readonly capacity: number,
    seed: readonly string[] = [],
  ) {
    this.entries = [...seed];
  }

  snapshot(): EchoBoundedSnapshot {
    const entries = [...this.entries];
    const used = boundedUsedChars(entries);
    return {
      target: this.target,
      header: boundedHeader(used, this.capacity),
      used_chars: used,
      capacity: this.capacity,
      entries,
    };
  }

  /** Unique normalised-substring match, exactly like the kernel. */
  private indexOfUnique(fragment: string): number {
    const needle = normalizeFa(fragment).trim();
    if (!needle) throw invalid('old must not be empty');
    const matches: number[] = [];
    this.entries.forEach((entry, index) => {
      if (normalizeFa(entry).includes(needle)) matches.push(index);
    });
    if (matches.length === 0) throw notFoundRefusal(fragment.trim());
    if (matches.length > 1) throw ambiguousRefusal(matches.length);
    return matches[0];
  }

  add(text: string): EchoBoundedSnapshot {
    const entry = text.trim();
    if (!entry) throw invalid('text must not be empty');
    const used = boundedUsedChars(this.entries);
    const needed = entry.length + (this.entries.length > 0 ? BOUNDED_SEPARATOR.length : 0);
    if (used + needed > this.capacity) {
      throw capacityRefusal(this.target, used + needed - this.capacity, this.snapshot().header);
    }
    this.entries.push(entry);
    return this.snapshot();
  }

  replace(old: string, next: string): EchoBoundedSnapshot {
    const entry = next.trim();
    if (!entry) throw invalid('new must not be empty');
    const index = this.indexOfUnique(old);
    const used = boundedUsedChars(this.entries);
    const delta = entry.length - this.entries[index].length;
    if (used + delta > this.capacity) {
      throw capacityRefusal(this.target, used + delta - this.capacity, this.snapshot().header);
    }
    this.entries[index] = entry;
    return this.snapshot();
  }

  remove(old: string): EchoBoundedSnapshot {
    const index = this.indexOfUnique(old);
    this.entries.splice(index, 1);
    return this.snapshot();
  }
}

/**
 * Lazily-created echo runtime for the `memory2.*` bridge family. The frozen
 * pair is captured once at construction and answers `memory2.status` forever.
 */
export class EchoMemory2Runtime {
  private stores: Record<EchoBoundedTarget, EchoBoundedStore>;
  private frozen: Record<EchoBoundedTarget, EchoBoundedSnapshot>;

  constructor(
    notesSeed: readonly string[] = [
      'User prefers concise replies, Persian first.',
      'Project Dream: the bridge speaks JSON-RPC 2.0 over stdio.',
    ],
    profileSeed: readonly string[] = ['Name: Sahar', 'Time zone: Asia/Tehran'],
  ) {
    this.stores = {
      memory: new EchoBoundedStore('memory', ECHO_NOTES_CAPACITY, notesSeed),
      user: new EchoBoundedStore('user', ECHO_PROFILE_CAPACITY, profileSeed),
    };
    this.frozen = {
      memory: this.stores.memory.snapshot(),
      user: this.stores.user.snapshot(),
    };
  }

  handles(method: string): boolean {
    return method.startsWith('memory2.');
  }

  handle(
    method: string,
    params: RpcParams,
  ): EchoBoundedSnapshot | Record<EchoBoundedTarget, EchoBoundedSnapshot> {
    switch (method) {
      case 'memory2.snapshot':
        if ('target' in params) return this.store(params).snapshot();
        return {
          memory: this.stores.memory.snapshot(),
          user: this.stores.user.snapshot(),
        };
      case 'memory2.status':
        if ('target' in params) {
          const target = this.wireTarget(params);
          return this.frozen[target];
        }
        return this.frozen;
      case 'memory2.add': {
        const store = this.store(params);
        if (typeof params['text'] !== 'string') throw invalid('text must be a string');
        return store.add(params['text']);
      }
      case 'memory2.replace': {
        const store = this.store(params);
        if (typeof params['old'] !== 'string' || typeof params['new'] !== 'string') {
          throw invalid('old and new must be strings');
        }
        return store.replace(params['old'], params['new']);
      }
      case 'memory2.remove': {
        const store = this.store(params);
        if (typeof params['old'] !== 'string') throw invalid('old must be a string');
        return store.remove(params['old']);
      }
      default:
        throw invalid(`unknown memory2 method ${method}`);
    }
  }

  private wireTarget(params: RpcParams): EchoBoundedTarget {
    const target = params['target'];
    if (target === 'memory' || target === 'user') return target;
    throw invalid("target must be 'memory' or 'user'");
  }

  private store(params: RpcParams): EchoBoundedStore {
    return this.stores[this.wireTarget(params)];
  }
}
