const $ = (id) => document.getElementById(id);
const t = window.t || ((s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s));

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} HTTP ${r.status}`);
  return r.json();
}

// Fetched JSON is cached so a language toggle re-renders without re-fetching.
let pathData = null;   // T.honors from /tournament.json
let fcData = null;     // /forecast.json

function boardTable(el, rows, unit) {
  el.innerHTML = `<thead><tr><th></th><th>${t('Player')}</th><th>${t('Team')}</th><th>${t('Pos')}</th>
      <th class="num">${unit}</th></tr></thead><tbody>` +
    rows.slice(0, 15).map((r, i) =>
      `<tr><td>${i + 1}</td><td>${r.player}</td><td class="mut">${r.team}</td>
       <td class="mut">${r.pos}</td><td class="num"><b>${r.exp.toFixed(2)}</b></td></tr>`).join('') +
    '</tbody>';
}

function renderPath() {
  const h = pathData;
  if (!h) return;
  $('pathMeta').textContent = '· ' + t('{n} goals on the modal path', { n: h.total_goals });
  boardTable($('bootTable'), h.golden_boot, 'xG');
  boardTable($('playTable'), h.playmaker, 'xA');
  if (h.golden_glove) {
    const g = h.golden_glove;
    $('glove').innerHTML = `🧤 <b>${t('Golden Glove pick:')}</b> ${g.player} (${g.team}) — ` +
      t('deepest-run defence, {conceded} goals conceded in {matches} predicted matches ({perMatch}/match).',
        { conceded: g.conceded, matches: g.matches, perMatch: g.per_match });
  }
}

function renderForecast() {
  const f = fcData;
  if (!f) return;
  $('fcMeta').textContent = '· ' + t('{n}k sims', { n: Math.round(f.sims / 1000) }) +
    ' · ~' + t('{n} goals', { n: Math.round(f.exp_total_goals) });
  const bars = (el, obj, k) => {
    const entries = Object.entries(obj).slice(0, k);
    const max = Math.max(...entries.map((e) => e[1]), 0.01);
    el.innerHTML = entries.map(([n, v]) =>
      `<div class="bar"><span class="lbl">${n}</span>
        <span class="track"><span class="fill" style="width:${(v / max * 100).toFixed(0)}%"></span></span>
        <span class="pct">${(v * 100).toFixed(0)}%</span></div>`).join('');
  };
  bars($('fcChampion'), f.champion, 12);
  bars($('fcBoot'), f.golden_boot, 10);
  bars($('fcPlay'), f.playmaker, 10);
}

async function loadPath() {
  const T = await getJSON('/tournament.json');
  pathData = T.honors;
  renderPath();
}

async function loadForecast() {
  fcData = await getJSON('/forecast.json');
  renderForecast();
}

// Re-render both boards from cached JSON on a language toggle (no re-fetch).
function rerender() {
  renderPath();
  renderForecast();
}
document.addEventListener('gf:langchange', rerender);

Promise.allSettled([loadPath(), loadForecast()]).then((rs) => {
  const bad = rs.filter((r) => r.status === 'rejected');
  if (bad.length) $('err').textContent = t('Error:') + ' ' + bad.map((b) => b.reason.message).join(' · ');
});
