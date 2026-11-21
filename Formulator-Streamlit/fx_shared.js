/* Shared by studio.html (the Studio page) and bench.html (the Formulation page):
   small helpers, the link to Streamlit, the data from the CSV files, and the formulation theory.
   The theory mirrors core.py. If you change a rule here, change it there too. */
window.FX = (function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const fmt = n => n == null ? "–" : (Math.abs(n) < 0.01 && n !== 0 ? n.toFixed(4) : n.toFixed(2)).replace(/\.?0+$/, "");
const phText = ph => ph[0] === ph[1] ? fmt(ph[0]) : `${fmt(ph[0])}–${fmt(ph[1])}`;

// ============================================================
// LINK TO STREAMLIT
// Outgoing: the page types a small JSON message into a hidden Streamlit text box.
// Incoming: Streamlit writes its reply into a hidden element, which the page re-reads when it changes.
// Opened on its own, without Streamlit, a page still works: the link simply stays off.
// ============================================================
function bridge(inboxLabel, outboxId) {
  const b = {on: false, data: null, raw: null, reads: 0, onUpdate: () => {}};
  const host = () => { try { return window.parent !== window ? window.parent : null; } catch (e) { return null; } };
  const inbox = () => { try { return host().document.querySelector(`input[aria-label="${inboxLabel}"]`); } catch (e) { return null; } };
  b.framed = () => !!host();
  b.read = () => {
    let el = null;
    try { el = host().document.getElementById(outboxId); } catch (e) {}
    b.on = !!(el && inbox());
    const raw = el ? el.textContent.trim() : null;
    if (raw === b.raw) return;
    b.raw = raw;
    try { b.data = raw ? JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(raw), c => c.charCodeAt(0)))) : null; } catch (e) { return; }
    b.onUpdate(b.data, b.reads++ === 0);
  };
  b.emit = (type, payload) => {
    const el = inbox(), w = host();
    if (!el) return false;
    const value = JSON.stringify({id: Date.now() + "-" + Math.random().toString(36).slice(2, 8), type, ...payload});
    Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new w.Event("input", {bubbles: true}));
    // Streamlit takes a text box's value when Enter is pressed or the box loses focus
    for (const name of ["keydown", "keypress", "keyup"]) el.dispatchEvent(new w.KeyboardEvent(name, {key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true}));
    el.dispatchEvent(new w.FocusEvent("focusout", {bubbles: true}));
    return true;
  };
  // re-read Streamlit's reply whenever the host page changes (and on a timer, as a fallback)
  b.start = () => {
    b.read(); setInterval(b.read, 400);
    try { const w = host(); if (w) new w.MutationObserver(b.read).observe(w.document.body, {childList: true, subtree: true, characterData: true}); } catch (e) {}
  };
  // wait a moment for Streamlit to draw its reply element, so the page can start from the saved state
  b.ready = async () => {
    for (let n = 0; n < 25 && b.framed(); n++) { b.read(); if (b.data) break; await new Promise(r => setTimeout(r, 80)); }
    return b.data;
  };
  // open another page of the app by pressing its link in Streamlit's menu, which keeps the visit's formulas
  b.go = path => {
    try {
      const a = [...host().document.querySelectorAll("header a[href], [data-testid='stSidebarNav'] a[href]")].find(x => new URL(x.href).pathname.replace(/\/$/, "").endsWith("/" + path));
      if (a) { a.click(); return true; }
    } catch (e) {}
    return false;
  };
  return b;
}

// ============================================================
// DATA
// ============================================================
function parseCSV(text) {
  const rows = []; let row = [], cell = "", q = false;
  text = text.replace(/^﻿/, "");
  for (let k = 0; k < text.length; k++) {
    const c = text[k];
    if (q) { if (c === '"') { if (text[k + 1] === '"') { cell += '"'; k++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[k + 1] === "\n") k++; row.push(cell); cell = ""; if (row.some(x => x !== "")) rows.push(row); row = []; }
    else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift();
  return rows.map(r => Object.fromEntries(head.map((h, n) => [h, r[n] ?? ""])));
}
async function loadData() {
  if (window.__DATA__) return window.__DATA__;
  const get = async f => parseCSV(await (await fetch("./" + f, {cache: "no-store"})).text());
  return {ingredients: await get("ingredients.csv"), products: await get("products.csv"), regulations: await get("regulations.csv")};
}

const ZONES = {oil: "Oil phase", water: "Water phase", cool: "Cool-down"};
const PALETTE = {
  oil: ["#F2FAFE", "#CDEBFA", "#A5DBF6", "#7FCBF2", "#DDF2FC", "#B9E3F8", "#92D3F4", "#6CC3F0"],
  water: ["#0297DE", "#0277B0", "#03A9F4", "#015F8C", "#0288C8"],
  cool: ["#FC734D", "#FFA588", "#E2552E", "#FFC4B0", "#F58A6A"],
};

function prepare(DATA) {
  const NUM = ["min", "typ", "max", "rhlb", "hlb", "ph_min", "ph_max", "spread", "grease", "tack", "body", "film", "dry"];
  const num = v => v === "" || v == null ? null : Number(v);
  const INGS = DATA.ingredients.map(r => {
    const i = {...r};
    NUM.forEach(k => { i[k] = num(i[k]); });
    i.qs = !!num(r.qs); i.unsaturated = !!num(r.unsaturated);
    i.products = (r.products || "").split(";").filter(Boolean);
    // the jobs it does in a formula, main job first (some ingredients do two)
    i.roles = (r.roles || r.cat || "").split(";").map(s => s.trim()).filter(Boolean);
    // where it sits in the bottle: oil on top, water in the middle, cool-down additions at the bottom
    i.zone = (i.cat === "Preservative" || i.cat === "pH adjuster" || i.phase === "Cool-down") ? "cool" : i.phase === "Oil" ? "oil" : "water";
    return i;
  });
  INGS.forEach(i => { const peers = INGS.filter(x => x.zone === i.zone); i.color = PALETTE[i.zone][peers.indexOf(i) % PALETTE[i.zone].length]; });
  const ING = Object.fromEntries(INGS.map(i => [i.id, i]));
  const PRODUCTS = DATA.products, CODES = PRODUCTS.map(p => p.code);
  const REGS = DATA.regulations.map(r => ({...r, limit: num(r.limit)}));
  const ROLES = [...new Set(INGS.filter(i => i.id !== "aqua").flatMap(i => i.roles))];
  const sum = xs => xs.reduce((s, i) => s + i.pct, 0);

  // the formula as a list: water first (whatever is left to 100%), then the ingredients in file order
  const itemsOf = a => [{...ING.aqua, pct: 100 - Object.values(a).reduce((s, p) => s + p, 0)}, ...INGS.filter(i => a[i.id] != null).map(i => ({...i, pct: a[i.id]}))];
  const allowed = (id, ptype) => !REGS.some(r => r.ingredient === id && r.rule === "prohibited" && ["Both", ptype].includes(r.applies_to));

  // ---- stability theory: each "high" check costs 20 points and each "warn" costs 7 ----
  // ph is [low, high], or null to leave the pH checks out. opts.rules === false leaves out the legal rules on file.
  function analyse(it, ptype, ph, opts = {}) {
    const checks = [], add = (l, t, d) => checks.push({l, t, d});
    if (it.length === 1) return {checks: [{l: "info", t: "Only water so far", d: "Add ingredients to see the stability checks."}], score: null};
    const w = it[0].pct;
    const oils = it.filter(i => i.phase === "Oil" && i.cat !== "Emulsifier"), emuls = it.filter(i => i.cat === "Emulsifier");
    const fatty = it.filter(i => i.cat === "Fatty alcohol"), pres = it.filter(i => i.cat === "Preservative");
    const oilT = sum(oils), emT = sum(emuls), fatT = sum(fatty), ids = it.map(i => i.id);
    if (w < 0) add("high", "Over 100%", `Non-water ingredients add up to ${fmt(100 - w)}%. Reduce some amounts.`);
    else if (w < 50) add("warn", "Low water content", `Water is only ${fmt(w)}%. Very low water can make an O/W emulsion too thick or flip it to W/O.`);
    else add("ok", "Total = 100%", `Water q.s. to ${fmt(w)}%.`);
    it.slice(1).forEach(i => {
      if (i.qs || i.min == null) return;
      if (i.pct > i.max) add("high", `${i.short} above usual maximum`, `${fmt(i.pct)}% is above the usual ${fmt(i.max)}%.`);
      else if (i.pct < i.min) add("warn", `${i.short} below usual level`, `${fmt(i.pct)}% may be too little to work (usual ${fmt(i.min)}–${fmt(i.max)}%).`);
    });
    if (oilT > 0 && !emuls.length) add("high", "No emulsifier", "Oil and water will separate. Add an emulsifier.");
    else if (oilT > 0) {
      const r = emT / oilT, txt = `Emulsifier is ${(r * 100).toFixed(0)}% of the oil phase (rule of thumb: about 15–30%).`;
      if (r < .10) add("high", "Too little emulsifier for the oil load", txt);
      else if (r < .15) add("warn", "Emulsifier on the low side", txt);
      else if (r > .40) add("warn", "Excess emulsifier", txt + " Too much can feel soapy or tacky.");
      else add("ok", "Emulsifier amount OK", txt);
    }
    const known = oils.filter(i => i.rhlb != null && i.pct > 0), unknown = oils.filter(i => i.rhlb == null && i.pct > 0);
    if (known.length && emuls.length && emT > 0) {
      const r = known.reduce((s, i) => s + i.rhlb * i.pct, 0) / sum(known), b = emuls.reduce((s, i) => s + i.hlb * i.pct, 0) / emT, d = Math.abs(r - b);
      add(d <= 1.5 ? "ok" : d <= 3 ? "warn" : "high", d <= 1.5 ? "HLB matched" : d <= 3 ? "HLB slightly off" : "HLB mismatch",
        `Oil phase needs HLB ≈ ${r.toFixed(1)}; the emulsifier blend gives ≈ ${b.toFixed(1)}. Indicative only.`);
    }
    if (unknown.length) add("info", "Missing required-HLB data", `${unknown.map(i => i.short).join(", ")} left out of the HLB calculation. Add the value from the supplier TDS.`);
    if (oilT > 0) {
      if (oilT < 5) add("warn", "Very light oil phase", `Oil phase ${fmt(oilT)}%: likely a thin, watery lotion.`);
      else if (oilT > 40) add("high", "Oil phase very high", `Oil phase ${fmt(oilT)}% is hard to keep stable as O/W.`);
      else if (oilT > 30) add("warn", "Rich oil phase", `Oil phase ${fmt(oilT)}%: needs a strong emulsifier system.`);
      else add("ok", "Oil phase in lotion range", `Oil phase ${fmt(oilT)}% (typical 10–30%).`);
    }
    if (oilT > 0 && fatT === 0) add("warn", "No fatty alcohol", "Without a thickener such as cetearyl alcohol the lotion stays thin and droplets can cream over time.");
    else if (fatT > 7) add("warn", "High fatty alcohol", `${fmt(fatT)}% may feel waxy and keep thickening during storage.`);
    if (ids.includes("cetstear") && ids.includes("cetearyl")) add("warn", "Duplicate ingredient", "Cetyl/Stearyl Alcohol and Cetearyl Alcohol are the same material. Keep only one.");
    it.forEach(i => { if (i.id === "shea" && i.pct > 5) add("warn", "Graininess risk", `Shea butter at ${fmt(i.pct)}% can form crystals. Cool the batch quickly while stirring.`); });
    const unsat = it.filter(i => i.unsaturated && i.pct > 0);
    if (unsat.length && !it.some(i => i.cat === "Antioxidant")) add("warn", "Rancidity risk", `${unsat.map(i => i.short).join(" and ")} can oxidise. Add an antioxidant such as tocopherol (0.1–0.5%).`);
    else if (unsat.length) add("ok", "Oils protected from rancidity", "An antioxidant is present alongside the unsaturated oils.");
    if (!pres.length) add("high", "No preservative", "Any water-based product will grow microbes. Add a preservative system.");
    if (ids.includes("mit") && pres.length === 1) add("warn", "Weak against yeast and mould", "MIT alone has poor antifungal activity. A second preservative is usually needed.");
    if (ids.includes("tapioca") && pres.length) add("info", "Starch raises microbial load", "Check preservative efficacy with a challenge test.");
    if (ph) it.forEach(i => {
      if (i.ph_min == null) return;
      const works = `${i.short} works best at pH ${fmt(i.ph_min)}–${fmt(i.ph_max)}`;
      if (ph[1] < i.ph_min || ph[0] > i.ph_max) add("warn", `pH outside ${i.short} range`, `Target pH ${phText(ph)}; ${works}.`);
      else if (ph[0] < i.ph_min || ph[1] > i.ph_max) add("info", `Keep the pH inside the ${i.short} range`, `${works}, which covers only part of your target pH ${phText(ph)}.`);
    });
    if (ids.includes("naoh") && !it.some(i => i.cat === "Acid / polymer")) add("info", "NaOH may not be needed", "Nothing acidic is in the formula yet. Add NaOH only if the measured pH is below target.");
    const ch = new Set(it.map(i => i.charge));
    if (ch.has("anionic") && ch.has("cationic")) add("high", "Charge incompatibility", "Anionic and cationic ingredients can react and destabilise the emulsion.");
    let score = 100 - 20 * checks.filter(c => c.l === "high").length - 7 * checks.filter(c => c.l === "warn").length;
    if (w < 0) score = 0;
    // rules on file (regulations.csv): shown, but not part of the stability score
    if (opts.rules !== false) {
      const hits = {};
      REGS.forEach(r => {
        const i = it.find(x => x.id === r.ingredient && x.pct > 0);
        if (!i || !["Both", ptype].includes(r.applies_to)) return;
        const bad = r.rule === "prohibited" ? `${i.short} is not allowed in ${ptype.toLowerCase()} products`
          : r.rule === "max_pct" && i.pct > r.limit ? `${i.short} is above the legal limit of ${fmt(r.limit)}%`
          : r.rule === "max_ph" && ph && ph[0] >= r.limit ? `Target pH must stay below ${fmt(r.limit)} for ${i.short}` : null;
        if (bad) (hits[bad] = hits[bad] || []).push(r.country);
      });
      Object.entries(hits).forEach(([t, cs]) => checks.push({l: "high", rule: true, t, d: `Rule on file for ${[...new Set(cs)].join(", ")}.`}));
    }
    return {checks, score: clamp(score, 0, 100)};
  }

  // the pH range in which every ingredient in the formula works, or null when none of them sets one
  function phWindow(it) {
    const set = it.filter(i => i.ph_min != null && i.pct > 0);
    return set.length ? [Math.max(...set.map(i => i.ph_min)), Math.min(...set.map(i => i.ph_max))] : null;
  }

  // emulsifier: about 22% of the oil phase, split by HLB when there are two
  function emulsifierLevels(a) {
    const oilIds = Object.keys(a).filter(i => ING[i].phase === "Oil" && ING[i].cat !== "Emulsifier");
    const emIds = Object.keys(a).filter(i => ING[i].cat === "Emulsifier");
    const oil = oilIds.reduce((s, i) => s + a[i], 0);
    const known = oilIds.filter(i => ING[i].rhlb != null);
    const kt = known.reduce((s, i) => s + a[i], 0);
    const rhlb = kt ? known.reduce((s, i) => s + ING[i].rhlb * a[i], 0) / kt : 10;
    let share = Object.fromEntries(emIds.map(i => [i, 1 / emIds.length]));
    if (emIds.length === 2) {
      const [x, y] = emIds.map(i => ING[i]);
      if (x.hlb !== y.hlb) { const s = clamp((rhlb - y.hlb) / (x.hlb - y.hlb), .3, .7); share = {[x.id]: s, [y.id]: 1 - s}; }
    }
    emIds.forEach(i => { a[i] = Math.round(clamp(share[i] * 0.22 * oil, ING[i].min, ING[i].max) * 10) / 10; });
  }

  // add what a basic O/W emulsion is missing and take out what cannot stay (the same rules as complete_formula in core.py)
  function complete(a, ptype, ph) {
    const ids = Object.keys(a), cats = new Set(ids.map(i => ING[i].cat)), added = [], removed = [];
    const want = id => { if (ING[id] && a[id] == null && !added.includes(id)) added.push(id); };
    if (!cats.has("Humectant")) want("glycerin");
    if (!cats.has("Emollient") && !cats.has("Butter")) want("coco");
    if (!cats.has("Fatty alcohol")) want("cetearyl");
    if (!cats.has("Emulsifier")) { want("glucoside"); if (ING.kcp && (!ph || (ING.kcp.ph_min <= ph[0] && ph[1] <= ING.kcp.ph_max))) want("kcp"); }
    if (ptype === "Rinse-off" && !cats.has("Preservative")) want("mit");
    if (ptype === "Leave-on" && a.mit != null) removed.push("mit");
    if (ptype === "Leave-on" && !ids.some(i => ING[i].cat === "Preservative" && i !== "mit")) want("pheno");
    if (!cats.has("Antioxidant") && [...ids, ...added].some(i => ING[i].unsaturated)) want("toco");
    if (a.cetstear != null && a.cetearyl != null) removed.push("cetstear");
    added.forEach(i => { a[i] = ING[i].typ ?? 1; });
    removed.forEach(i => { delete a[i]; });
    if (added.some(i => ING[i].cat === "Emulsifier")) emulsifierLevels(a);
    return {added, removed};
  }

  // theory-based first draft: fill the gaps, typical levels, oil phase at most 25%, emulsifier matched to it
  function suggest(a, ptype, ph) {
    const change = complete(a, ptype, ph), ids = Object.keys(a);
    ids.forEach(i => { a[i] = ING[i].typ ?? 1; });
    const oilIds = ids.filter(i => ING[i].phase === "Oil" && ING[i].cat !== "Emulsifier");
    const oil = oilIds.reduce((s, i) => s + a[i], 0);
    if (oil > 25) {   // many oils: trim the emollients and butters, not the fatty alcohol
      const soft = oilIds.filter(i => ["Emollient", "Butter"].includes(ING[i].cat)), softT = soft.reduce((s, i) => s + a[i], 0);
      const scale = Math.max(0, softT - (oil - 25)) / softT;
      soft.forEach(i => { a[i] = Math.round(Math.max(ING[i].min, ING[i].typ * scale) * 10) / 10; });
    }
    emulsifierLevels(a);
    return change;
  }
  const names = ids => ids.map(i => ING[i].short.replace(/\.$/, "")).join(", ");

  return {INGS, ING, PRODUCTS, CODES, REGS, ROLES, ZONES, itemsOf, allowed, analyse, phWindow, emulsifierLevels, complete, suggest, names};
}

return {$, $$, esc, clamp, fmt, phText, bridge, parseCSV, loadData, prepare, ZONES};
})();
