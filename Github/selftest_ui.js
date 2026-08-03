#!/usr/bin/env node
/* selftest_ui.js — headless check of the live-ledger panel.
 *
 * WHY THIS FILE EXISTS. This repo has a real build-time integrity guard
 * (validate_build.py) covering the ratings payload, and NOTHING covering the render
 * layer -- the JavaScript that turns ledger.json into the only sentence on the site
 * that says whether the model actually works. Two defects from the sibling repos
 * apply directly here:
 *
 *   1. A panel written into a DOM id that does not exist renders nothing and looks
 *      exactly like a panel with no data. (MLBTool shipped 87 lines of calibration
 *      that way for months.)
 *   2. A model figure over one game set printed next to a market figure over another,
 *      captioned "on the same bouts". That caption was live here: L.acc is over every
 *      settled bout, market.acc only over the ones that carried a devigged consensus.
 *
 * It also pins the verdict language. The forward record is 11 bouts at 36.4% with the
 * market at 81.8% and the model 0-for-5 head to head. A page that reports those three
 * numbers without saying what they mean is technically honest and practically
 * misleading, and a page that says it without stating n=11 is the opposite mistake.
 * Both halves are asserted below so a future edit cannot quietly drop either one.
 *
 * The TEMPLATE is the source of truth (build_widget renders it into
 * output/ufc_skill_explorer.html, build_site copies that to docs/index.html), so the
 * template is what gets exercised -- and then docs/ is checked to carry the same
 * panel, which is what catches a shipped build that predates a template edit.
 */
const fs = require('fs');
const path = require('path');
const HERE = __dirname;

let failures = 0;
const fail = m => { console.log('  FAIL: ' + m); failures++; };
const ok = m => console.log('  ok: ' + m);
const check = (c, m) => (c ? ok(m) : fail(m));

const TEMPLATE = path.join(HERE, 'ufc_skill_explorer_template.html');
const tpl = fs.readFileSync(TEMPLATE, 'utf8');

/* Pull the ledger IIFE out of the shipped markup. */
function ledgerScript(html, label) {
  const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  const hit = blocks.filter(b => /ll_body/.test(b));
  if (hit.length !== 1) {
    fail(`${label}: expected exactly 1 script block touching ll_body, found ${hit.length}`);
    return null;
  }
  return hit[0];
}

/* IDS THAT REALLY EXIST. getElementById must return null for anything not in the
 * markup -- inventing elements on demand is precisely what hides bug class 1 above. */
function realIds(html) {
  return new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
}

function runLedger(src, html, ledger) {
  const IDS = realIds(html);
  const els = {};
  const mk = id => ({ id, innerHTML: '', textContent: '', style: {},
    classList: { add() {}, remove() {}, toggle() {} }, appendChild() {},
    querySelectorAll: () => [], querySelector: () => null, addEventListener() {} });
  const doc = {
    getElementById: id => (IDS.has(id) ? (els[id] || (els[id] = mk(id))) : null),
    querySelectorAll: () => [], querySelector: () => null,
    createElement: () => mk('_tmp'), addEventListener() {}, body: mk('body'),
  };
  const errors = [];
  const fetched = [];
  const sandbox = {
    document: doc,
    window: { addEventListener() {} },
    console: { log() {}, warn() {}, error: (...a) => errors.push(a.map(String).join(' ')) },
    fetch: (url, opt) => { fetched.push([String(url), opt || {}]);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(ledger) }); },
    setTimeout, Math, JSON, Date, Number, String, Array, Object, Boolean,
    isFinite, isNaN, parseFloat, parseInt,
  };
  const names = Object.keys(sandbox);
  new Function(...names, src)(...names.map(n => sandbox[n]));
  return {
    errors, fetched, els,
    settle: async () => { for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r)); },
    body: () => (els.ll_body ? els.ll_body.innerHTML : null),
    shown: () => (els.liveledger ? els.liveledger.style.display : undefined),
  };
}

const SRC = ledgerScript(tpl, 'template');
if (!SRC) process.exit(1);

/* The record as actually committed. */
const LEDGER = JSON.parse(fs.readFileSync(path.join(HERE, 'output', 'ledger.json'), 'utf8'));

(async () => {

/* ------------------------------------ 0) the panel writes to elements that exist */
console.log('0) the panel writes only to ids that are really in the markup');
{
  const IDS = realIds(tpl);
  const targets = [...SRC.matchAll(/getElementById\('([A-Za-z0-9_-]+)'\)/g)].map(m => m[1]);
  const missing = [...new Set(targets)].filter(id => !IDS.has(id));
  check(targets.length > 0, 'found the getElementById targets');
  check(missing.length === 0, 'no getElementById points at a nonexistent element'
    + (missing.length ? ' — MISSING: ' + missing.join(', ') : ''));
}

/* -------------------------------------------- 1) the committed ledger renders */
console.log('1) the committed ledger.json renders');
{
  const r = runLedger(SRC, tpl, JSON.parse(JSON.stringify(LEDGER)));
  await r.settle();
  check(r.errors.length === 0, 'no console errors' + (r.errors.length ? ': ' + r.errors[0] : ''));
  const h = r.body() || '';
  check(h.length > 60, 'the panel painted');
  check(r.shown() === '', 'and the section was un-hidden');
  check(!/undefined|NaN/.test(h), 'no "undefined"/"NaN" in the panel');
  check(new RegExp('<b>' + LEDGER.n + '</b> settled bouts').test(h),
    'it states the number of settled bouts (' + LEDGER.n + ')');
}

/* ------------------------- 2) model and market are quoted over the SAME bouts */
console.log('2) the market comparison compares one bout set');
{
  // Force model_acc apart from the overall acc so the panel cannot pass by quoting
  // L.acc -- which is what it used to do, under the caption "on the same bouts".
  const L = { n: 14, voids: 1, events: 4, acc: 42.9, brier: 0.2650,
    market: { n: 11, acc: 81.8, model_acc: 36.4,
              disagree_n: 5, disagree_model_right: 0.0, disagree_market_right: 100.0 } };
  const r = runLedger(SRC, tpl, L); await r.settle();
  const h = r.body() || '';
  check(/model <b>36\.4%<\/b>/.test(h),
    "it quotes the model on the MARKET's own subset (model_acc), not over every settled bout");
  check(!/same <b>11<\/b> bouts: model <b>42\.9%/.test(h), 'and specifically not the all-bouts figure');
  check(/market <b>81\.8%<\/b>/.test(h), 'the market beside it');
  check(/same <b>11<\/b> bouts/.test(h), 'it names the bout set both figures are over');
  check(/model right <b[^>]*>0%<\/b>/.test(h), "the model's rate on the disagreements");
  check(/market right <b>100%<\/b>/.test(h),
    'and how often the MARKET was right on those same bouts — the half this panel never carried');
  check(!/undefined|NaN/.test(h), 'no "undefined"/"NaN"');
}

/* ------------------------------------ 3) the verdict is stated, and so is the n */
console.log('3) a model losing to the price says so, with the sample size');
{
  const r = runLedger(SRC, tpl, JSON.parse(JSON.stringify(LEDGER))); await r.settle();
  const h = r.body() || '';
  check(/the market is the better forecast/.test(h),
    'the page says the market is the better forecast rather than leaving it to be inferred');
  check(/has not won yet/.test(h),
    'and that taking the model\'s side against the price has not won yet (0 for 5)');
  check(/far too few to measure a model by/.test(h),
    'and it says n=' + LEDGER.n + ' is far too few — the verdict is a direction, not a measurement');
  check(/not as an edge/.test(h), 'and does not present the record as an edge');
}

/* ---------------------------------- 4) a model BEATING the price is not warned */
console.log('4) the verdict is earned, not automatic');
{
  const L = { n: 40, voids: 0, events: 8, acc: 70.0, brier: 0.1900,
    market: { n: 40, acc: 65.0, model_acc: 70.0,
              disagree_n: 10, disagree_model_right: 60.0, disagree_market_right: 40.0 } };
  const r = runLedger(SRC, tpl, L); await r.settle();
  const h = r.body() || '';
  check(!/the market is the better forecast/.test(h),
    'a model ahead of the price is NOT told it is behind (test is market>model, not model<50)');
  check(/model right <b[^>]*>60%<\/b>/.test(h), 'and its winning disagreement rate still prints');
}

/* --------------------------------------- 5) older / degraded ledgers still render */
console.log('5) degraded ledgers do not break the panel');
{
  // A ledger written before model_acc / disagree_market_right existed.
  const L = JSON.parse(JSON.stringify(LEDGER));
  delete L.market.model_acc; delete L.market.disagree_market_right;
  let r = runLedger(SRC, tpl, L); await r.settle();
  let h = r.body() || '';
  check(!/undefined|NaN/.test(h), 'an older market block renders with no "undefined"/"NaN"');
  check(new RegExp('model <b>' + LEDGER.acc + '%</b>').test(h),
    'and falls back to the overall accuracy rather than blank');

  // Nothing settled yet -- the pre-fight state.
  r = runLedger(SRC, tpl, { n: 0, voids: 0, events: 2 }); await r.settle();
  h = r.body() || '';
  check(r.errors.length === 0 && /card\(s\) logged pre-fight/.test(h),
    'a ledger with nothing settled renders the pre-fight message');
  check(!/undefined|NaN/.test(h), 'with no "undefined"/"NaN"');

  // Settled bouts but no market block at all (no prices were captured).
  r = runLedger(SRC, tpl, { n: 3, voids: 0, events: 1, acc: 66.7, brier: 0.21 });
  await r.settle();
  h = r.body() || '';
  check(r.errors.length === 0 && /<b>3<\/b> settled bouts/.test(h),
    'a ledger with no market block still reports the model record');
  check(!/undefined|NaN/.test(h), 'with no "undefined"/"NaN"');
}

/* ------------------------------------------------ 6) no stale-cache ledger fetch */
console.log('6) the ledger cannot be served from browser cache');
{
  const r = runLedger(SRC, tpl, JSON.parse(JSON.stringify(LEDGER))); await r.settle();
  check(r.fetched.length === 1 && /ledger\.json/.test(r.fetched[0][0]), 'it fetched ledger.json');
  check(/no-store/.test(JSON.stringify(r.fetched[0][1])),
    "the ledger fetch passes cache:'no-store'");
}

/* -------------------------------- 7) what is SHIPPED matches the template source */
console.log('7) the built docs/ carry the panel the template defines');
{
  // build_widget renders the template into output/, build_site copies it into docs/.
  // A template edit that was never rebuilt ships the old panel while every check
  // above passes, so compare the actual bytes that go to Pages.
  for (const rel of ['docs/index.html', 'docs/phone.html',
                     'output/ufc_skill_explorer.html', 'output/ufc_skill_explorer_phone.html']) {
    const p = path.join(HERE, rel);
    if (!fs.existsSync(p)) { fail(rel + ' does not exist'); continue; }
    const built = ledgerScript(fs.readFileSync(p, 'utf8'), rel);
    check(built !== null && built.trim() === SRC.trim(),
      rel + ' carries the same ledger panel as the template (rebuild if this fails)');
  }
}

console.log(failures ? `\nUFC UI SELFTEST: ${failures} FAILURE(S)`
  : '\nUFC UI SELFTEST PASS — the live record quotes the model and the market over the '
  + 'same bouts, states both halves of the disagreement, and says plainly that the price '
  + 'is ahead on a sample far too small to call it');
process.exit(failures ? 1 : 0);

})();
