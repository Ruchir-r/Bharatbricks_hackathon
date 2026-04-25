/* i18n.js — runtime page-wide translation.
 *
 * Loads /static/translations.json once, walks every text node in the document,
 * and replaces matched strings with the chosen language. Re-applies after any
 * DOM mutation so dynamically-loaded cards (savings, schemes, refills) translate
 * too.
 *
 * Usage from app.js:
 *   await window.rxI18n.init();
 *   window.rxI18n.apply('ml');     // 'en' | 'hi' | 'ml'
 *
 * The current language persists in localStorage `rx_ui_lang`. Default is 'en'.
 */

(() => {
  const STORE_KEY = 'rx_ui_lang';
  const SUPPORTED = ['en', 'hi', 'ml'];

  let TABLE = null;          // { source_text → { en, hi, ml } }
  let CURRENT = null;        // 'en' | 'hi' | 'ml'
  let ORIGINAL_BY_NODE = new WeakMap();  // textNode → original textContent

  async function load() {
    if (TABLE) return TABLE;
    try {
      const r = await fetch('/static/translations.json', { cache: 'force-cache' });
      TABLE = await r.json();
    } catch (e) {
      console.warn('i18n: failed to load translations.json', e);
      TABLE = {};
    }
    return TABLE;
  }

  function lookup(text, lang) {
    const trimmed = (text || '').trim();
    if (!trimmed) return null;
    const entry = TABLE[trimmed];
    if (entry && entry[lang]) return entry[lang];
    return null;
  }

  function isVisibleTextNode(node) {
    if (node.nodeType !== Node.TEXT_NODE) return false;
    const parent = node.parentElement;
    if (!parent) return false;
    const tag = parent.tagName;
    // Skip script / style / textarea — replacing those breaks behaviour
    if (['SCRIPT', 'STYLE', 'TEXTAREA', 'NOSCRIPT', 'CODE', 'PRE'].includes(tag)) return false;
    // Skip the demo-mode badge and offline-cache pill (they're already English)
    if (parent.id === 'rx-demo-badge' || parent.id === 'rx-cached-pill') return false;
    return true;
  }

  function applyToNode(node, lang) {
    if (!isVisibleTextNode(node)) return;
    let original = ORIGINAL_BY_NODE.get(node);
    if (original === undefined) {
      original = node.textContent;
      ORIGINAL_BY_NODE.set(node, original);
    }
    const translated = lookup(original, lang);
    if (translated) {
      node.textContent = translated;
    } else if (lang === 'en' && /[ऀ-ॿ]/.test(original)) {
      // English mode but the source had Devanagari and we have no entry: leave original
      // (better to show Hindi than nothing)
      node.textContent = original;
    } else if (lang === 'ml' && original === node.textContent) {
      // No table entry for this node in Malayalam — leave it
    } else {
      node.textContent = original;
    }
  }

  function walk(root, lang) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = w.nextNode())) applyToNode(n, lang);
  }

  // Also translate placeholder + aria-label + title for matched English strings
  function walkAttributes(root, lang) {
    const els = root.querySelectorAll('[placeholder], [aria-label], [title]');
    els.forEach(el => {
      ['placeholder', 'aria-label', 'title'].forEach(attr => {
        // Dataset keys can't have dashes — convert "aria-label" → "ariaLabel"
        const slot = 'origAttr' + attr.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        const cur = el.getAttribute(attr);
        if (cur === null) return;
        if (!el.dataset[slot]) el.dataset[slot] = cur;
        const t = lookup(el.dataset[slot], lang);
        el.setAttribute(attr, t || el.dataset[slot]);
      });
    });
  }

  async function apply(lang) {
    if (!SUPPORTED.includes(lang)) lang = 'en';
    await load();
    CURRENT = lang;
    try { localStorage.setItem(STORE_KEY, lang); } catch {}
    document.documentElement.lang = lang;
    walk(document.body, lang);
    walkAttributes(document.body, lang);
    // Notify any feature-specific JS that wants to swap dynamic content
    window.dispatchEvent(new CustomEvent('rx-lang-changed', { detail: { lang } }));
  }

  function getLang() {
    if (CURRENT) return CURRENT;
    try {
      const saved = localStorage.getItem(STORE_KEY);
      if (SUPPORTED.includes(saved)) return saved;
    } catch {}
    // Browser locale fallback
    const nav = (navigator.language || 'en').toLowerCase();
    if (nav.startsWith('hi')) return 'hi';
    if (nav.startsWith('ml')) return 'ml';
    return 'en';
  }

  // MutationObserver: re-translate any newly-added DOM
  let observer = null;
  function startObserver() {
    if (observer) return;
    observer = new MutationObserver((muts) => {
      if (!CURRENT) return;
      for (const m of muts) {
        m.addedNodes.forEach(n => {
          if (n.nodeType === Node.TEXT_NODE) applyToNode(n, CURRENT);
          else if (n.nodeType === Node.ELEMENT_NODE) {
            walk(n, CURRENT);
            walkAttributes(n, CURRENT);
          }
        });
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  async function init() {
    await load();
    const lang = getLang();
    await apply(lang);
    startObserver();
  }

  window.rxI18n = { init, apply, getLang, SUPPORTED };
})();
