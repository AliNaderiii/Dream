const PERSIAN = /[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]/;

/** Detect the base direction while ignoring inline-code islands. */
export function textDirection(text: string): 'rtl' | 'ltr' {
  return PERSIAN.test(text.replace(/`[^`]*`/g, '')) ? 'rtl' : 'ltr';
}
