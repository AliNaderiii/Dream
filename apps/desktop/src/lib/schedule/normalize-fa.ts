/**
 * Persian/Arabic text normalisation — a TypeScript mirror of
 * `dream.memory.normalize_fa`.
 *
 * Steps run in the same fixed order as the Python original: NFKC, digit
 * folding, character unification, diacritic stripping, ZWNJ to space,
 * whitespace collapsing. Keeping the two implementations byte-compatible is
 * what lets the schedule parser below agree with the sidecar on every input.
 */

/** Persian (U+06F0–U+06F9) and Arabic-Indic (U+0660–U+0669) digits to ASCII. */
const DIGIT_MAP = new Map<string, string>();
for (let i = 0; i < 10; i += 1) {
  DIGIT_MAP.set(String.fromCodePoint(0x06f0 + i), String(i));
  DIGIT_MAP.set(String.fromCodePoint(0x0660 + i), String(i));
}

/** Arabic letter forms unified onto their Persian counterparts. */
const CHAR_MAP = new Map<string, string>([
  ['\u064a', '\u06cc'], // ARABIC YEH            -> FARSI YEH
  ['\u0649', '\u06cc'], // ALEF MAKSURA          -> FARSI YEH
  ['\u0643', '\u06a9'], // ARABIC KAF            -> KEHEH
  ['\u0629', '\u0647'], // TEH MARBUTA           -> HEH
  ['\u0623', '\u0627'], // ALEF WITH HAMZA ABOVE -> ALEF
  ['\u0625', '\u0627'], // ALEF WITH HAMZA BELOW -> ALEF
  ['\u0622', '\u0627'], // ALEF WITH MADDA ABOVE -> ALEF
  ['\u0624', '\u0648'], // WAW WITH HAMZA        -> WAW
  ['\u0626', '\u06cc'], // YEH WITH HAMZA        -> FARSI YEH
]);

/** Harakat, superscript alef and tatweel carry no lexical weight here. */
const DIACRITICS = /[\u064b-\u0652\u0670\u0640]/g;

const ZWNJ = /\u200c/g;
const WHITESPACE = /\s+/g;

/** Normalises Persian/Arabic text to one canonical spelling. */
export function normalizeFa(text: string): string {
  if (!text) return '';
  let out = text.normalize('NFKC');
  out = out.replace(/[\u06f0-\u06f9\u0660-\u0669]/g, (ch) => DIGIT_MAP.get(ch) ?? ch);
  out = out.replace(
    /[\u064a\u0649\u0643\u0629\u0623\u0625\u0622\u0624\u0626]/g,
    (ch) => CHAR_MAP.get(ch) ?? ch,
  );
  out = out.replace(DIACRITICS, '');
  out = out.replace(ZWNJ, ' ');
  return out.replace(WHITESPACE, ' ').trim();
}
