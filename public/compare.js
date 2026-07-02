const $ = (id) => document.getElementById(id);
const t = window.t || ((s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s));
let A, GROUPS;

async function load() {
  const r = await fetch('/actual.json');
  if (!r.ok) throw new Error(`actual.json HTTP ${r.status}`);
  A = await r.json();
  GROUPS = Object.keys(A.groups).sort();
  document.querySelectorAll('.viewtab').forEach((b) => {
    b.onclick = () => { location.hash = b.dataset.view === 'bracket' ? 'bracket' : 'groups'; };
  });
  window.addEventListener('hashchange', route);
  document.addEventListener('gf:langchange', render);   // re-translate in place, no re-fetch
  render();
  countUp();
}

// Full re-render from the cached JSON (A). Hooked to gf:langchange so a language
// toggle re-translates every panel without re-fetching.
function render() {
  $('asof').textContent = t('results through {d}', { d: A.as_of });
  renderStats(A.metrics);
  renderChamp(A.metrics);
  route();
}

function route() {
  const h = location.hash.slice(1);
  if (h === 'bracket') return showBracket();
  if (h.startsWith('group-') && A.groups[h.slice(6)]) return showGroups(h.slice(6));
  return showGroups(null);
}

const setTab = (v) => document.querySelectorAll('.viewtab')
  .forEach((b) => b.classList.toggle('active', b.dataset.view === v));

const pctTxt = (x) => (x * 100).toFixed(0) + '%';

function tile(emoji, big, label, sub, tone, count) {
  return `<div class="tile tile-${tone}">
    <div class="tile-emoji">${emoji}</div>
    <div class="tile-big"${count != null ? ` data-count="${count}"` : ''}>${big}</div>
    <div class="tile-label">${label}</div><div class="tile-sub">${sub}</div></div>`;
}

function renderStats(m) {
  const beat = m.rps < m.rps_baserate;
  const scored = m.group_matches_scored;
  const br = m.rps_baserate.toFixed(3);
  $('stats').innerHTML =
    tile('🎯', pctTxt(m.outcome_acc), t('Outcome accuracy'), t('{n}/{m} W/D/L correct', { n: Math.round(m.outcome_acc * scored), m: scored }), 'violet', m.outcome_acc * 100) +
    tile('🔢', pctTxt(m.exact_acc), t('Exact scoreline'), t('{n}/{m} spot-on', { n: Math.round(m.exact_acc * scored), m: scored }), 'sky', m.exact_acc * 100) +
    tile('📈', m.rps.toFixed(3), t('RPS on real games'), beat ? t('beats base-rate {r}', { r: br }) + ' ✓' : t('vs base-rate {r}', { r: br }), 'teal') +
    tile('🎟️', `${m.advancers_correct}/${m.advancers_total}`, t('Qualifiers called'), t('plus {n}/{m} group top-2', { n: m.top2_correct, m: m.top2_total }), 'amber') +
    tile(m.champion_alive ? '💚' : '💔', m.champion_alive ? t('Alive') : t('Out'), t('Predicted champion'), m.champion, m.champion_alive ? 'green' : 'coral');
}

function renderChamp(m) {
  const status = m.champion_alive
    ? `<span class="alive">${t('still in the tournament')}</span> 💚`
    : `<span class="dead">${t('already eliminated')}</span> 💔`;
  $('champ').innerHTML = `<p class="champ-line">${t(
    'Our pre-tournament pick <b>{champ}</b> is {status}. Across the 12 groups we correctly placed <b>{top2}</b> of the top-two spots and <b>{r32}</b> of the eventual round-of-32 teams.',
    { champ: m.champion, status, top2: `${m.top2_correct}/${m.top2_total}`, r32: `${m.advancers_correct}/${m.advancers_total}` },
  )}</p>`;
}

function showGroups(g) {
  setTab('groups');
  $('view-bracket').hidden = true;
  $('view-groups').hidden = false;
  g ? renderGroupDetail(g) : renderOverview();
}

function showBracket() {
  setTab('bracket');
  $('view-groups').hidden = true;
  $('view-bracket').hidden = false;
  const byMid = {};
  for (const [id, m] of Object.entries(A.bracket || {})) {
    byMid[id] = { home: m.home, away: m.away, winner: m.winner, live: m.played === false && m.home && m.away,
      hs: m.actual ? m.actual[0] : null, as: m.actual ? m.actual[1] : null,
      pens: m.pens, decided: m.decided };
  }
  renderBracket($('bracket'), byMid, { champion: A.champion_actual, championLabel: t('Champion (TBD)') });
}

const pills = (active) => `<div class="gsel"><span class="gsel-lbl">${t('Group')}</span>` +
  GROUPS.map((g) => `<button class="gpill ${g === active ? 'active' : ''}"
    onclick="location.hash='group-${g}'">${g}</button>`).join('') +
  (active ? `<button class="gpill" onclick="location.hash='groups'">${t('All')} ▸</button>` : '') + `</div>`;

const miniRow = (r, i, advSet) =>
  `<tr class="${advSet.has(r.team) ? 'adv' : ''}"><td>${i + 1}</td><td class="tname">${r.team}</td>
    <td>${r.w}-${r.d}-${r.l}</td><td>${r.gf}:${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
    <td><b>${r.pts}</b></td></tr>`;

function renderOverview() {
  const advSet = new Set(A.advancers.actual);
  const cards = GROUPS.map((g) => {
    const rows = A.groups[g].actual_table.map((r, i) => miniRow(r, i, advSet)).join('');
    return `<div class="gcard clickable" onclick="location.hash='group-${g}'">
      <div class="gc-head"><h3>${t('Group {g}', { g })}</h3><span class="gc-go">${t('predicted vs actual')} →</span></div>
      <table class="gtable">
        <thead><tr><th></th><th>${t('Team (actual)')}</th><th>${t('W-D-L')}</th><th>${t('GF:GA')}</th><th>${t('GD')}</th><th>${t('Pts')}</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
  }).join('');
  const badge = `<span class="tag tag-adv">${t('advanced')}</span>`;
  $('groupsPanel').innerHTML = `
    <h2>📊 ${t('Group stage — final tables')}</h2>
    <p class="hint">${t('The real 2026 group tables. {badge} reached the round of 32. Click a group to see our prediction beside reality, match by match.', { badge })}</p>
    ${pills(null)}
    <div class="groups-grid" style="margin-top:14px">${cards}</div>`;
}

const scoreCell = (arr, cls) => arr
  ? `<span class="sc ${cls}">${arr[0]}–${arr[1]}</span>` : `<span class="sc sc-pending">·</span>`;

function matchRow(mm) {
  const done = !!mm.actual;
  let badge = `<span class="badge badge-pending">${t('upcoming')}</span>`;
  if (done) {
    badge = mm.exact_hit ? `<span class="badge badge-exact">${t('exact')} ✓✓</span>`
      : mm.outcome_hit ? `<span class="badge badge-ok">${t('outcome')} ✓</span>`
        : `<span class="badge badge-miss">${t('miss')} ✗</span>`;
  }
  return `<div class="cmp-row ${done ? '' : 'is-pending'}">
    <span class="cmp-home">${mm.home}</span>
    <span class="cmp-scores">${scoreCell(mm.pred, 'sc-pred')}<span class="sc-vs">→</span>${scoreCell(mm.actual, 'sc-real')}</span>
    <span class="cmp-away">${mm.away}</span>${badge}</div>`;
}

function miniTable(rows, advSet, isActual) {
  const body = rows.map((r, i) => {
    const tag = advSet.has(r.team) ? ` <span class="tag tag-adv">${t('adv')}</span>` : '';
    return `<tr class="${i < 2 ? 'row-top2' : ''} ${advSet.has(r.team) ? 'row-adv' : ''}">
      <td class="rk">${i + 1}</td><td class="tn">${r.team}${tag}</td>
      <td><b>${r.pts}</b></td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td></tr>`;
  }).join('');
  return `<table class="cmp-table">
    <thead><tr><th></th><th>${isActual ? t('Actual') : t('Predicted')}</th><th>${t('Pts')}</th><th>${t('GD')}</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

function renderGroupDetail(g) {
  const blk = A.groups[g];
  const advSet = new Set(A.advancers.actual);
  const predAdv = new Set(A.advancers.predicted);
  $('groupsPanel').innerHTML = `
    <button class="grp-back" onclick="location.hash='groups'">← ${t('All groups')}</button>
    ${pills(g)}
    <div class="grp-title" style="margin-top:12px">${t('Group {g}', { g })}</div>
    <div class="cmp-tables" style="max-width:760px">
      <div class="cmp-col"><div class="cmp-cap cap-pred">${t('Predicted')}</div>${miniTable(blk.pred_table, predAdv, false)}</div>
      <div class="cmp-col"><div class="cmp-cap cap-real">${t('Actual')}</div>${miniTable(blk.actual_table, advSet, true)}</div>
    </div>
    <h3 style="margin-top:18px">${t('All six matches — our score → real score')}</h3>
    <div class="cmp-matches cmp-matches-grid">${blk.matches.map(matchRow).join('')}</div>`;
}

function countUp() {
  document.querySelectorAll('.tile-big[data-count]').forEach((el) => {
    const target = parseFloat(el.dataset.count);
    if (!isFinite(target) || !el.textContent.trim().endsWith('%')) return;
    let t0 = null;
    const tick = (ts) => {
      t0 = t0 ?? ts;
      const k = Math.min((ts - t0) / 800, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3))) + '%';
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

load().catch((e) => ($('err').textContent = t('Error: {msg}', { msg: e.message })));
