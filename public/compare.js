const $ = (id) => document.getElementById(id);
let A, GROUPS;

async function load() {
  const r = await fetch('/actual.json');
  if (!r.ok) throw new Error(`actual.json HTTP ${r.status}`);
  A = await r.json();
  GROUPS = Object.keys(A.groups).sort();
  $('asof').textContent = `results through ${A.as_of}`;
  renderStats(A.metrics);
  renderChamp(A.metrics);
  document.querySelectorAll('.viewtab').forEach((b) => {
    b.onclick = () => { location.hash = b.dataset.view === 'bracket' ? 'bracket' : 'groups'; };
  });
  window.addEventListener('hashchange', route);
  route();
  countUp();
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
  $('stats').innerHTML =
    tile('🎯', pctTxt(m.outcome_acc), 'Outcome accuracy', `${Math.round(m.outcome_acc * scored)}/${scored} W/D/L correct`, 'violet', m.outcome_acc * 100) +
    tile('🔢', pctTxt(m.exact_acc), 'Exact scoreline', `${Math.round(m.exact_acc * scored)}/${scored} spot-on`, 'sky', m.exact_acc * 100) +
    tile('📈', m.rps.toFixed(3), 'RPS on real games', `${beat ? 'beats' : 'vs'} base-rate ${m.rps_baserate.toFixed(3)} ${beat ? '✓' : ''}`, 'teal') +
    tile('🎟️', `${m.advancers_correct}/${m.advancers_total}`, 'Qualifiers called', `plus ${m.top2_correct}/${m.top2_total} group top-2`, 'amber') +
    tile(m.champion_alive ? '💚' : '💔', m.champion_alive ? 'Alive' : 'Out', 'Predicted champion', m.champion, m.champion_alive ? 'green' : 'coral');
}

function renderChamp(m) {
  $('champ').innerHTML = `<p class="champ-line">Our pre-tournament pick <b>${m.champion}</b> is
    ${m.champion_alive ? '<span class="alive">still in the tournament</span> 💚'
      : '<span class="dead">already eliminated</span> 💔'}.
    Across the 12 groups we correctly placed <b>${m.top2_correct}/${m.top2_total}</b> of the top-two
    spots and <b>${m.advancers_correct}/${m.advancers_total}</b> of the eventual round-of-32 teams.</p>`;
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
  renderBracket($('bracket'), byMid, { champion: A.champion_actual, championLabel: 'Champion (TBD)' });
}

const pills = (active) => `<div class="gsel"><span class="gsel-lbl">Group</span>` +
  GROUPS.map((g) => `<button class="gpill ${g === active ? 'active' : ''}"
    onclick="location.hash='group-${g}'">${g}</button>`).join('') +
  (active ? `<button class="gpill" onclick="location.hash='groups'">All ▸</button>` : '') + `</div>`;

const miniRow = (r, i, advSet) =>
  `<tr class="${advSet.has(r.team) ? 'adv' : ''}"><td>${i + 1}</td><td class="tname">${r.team}</td>
    <td>${r.w}-${r.d}-${r.l}</td><td>${r.gf}:${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
    <td><b>${r.pts}</b></td></tr>`;

function renderOverview() {
  const advSet = new Set(A.advancers.actual);
  const cards = GROUPS.map((g) => {
    const rows = A.groups[g].actual_table.map((r, i) => miniRow(r, i, advSet)).join('');
    return `<div class="gcard clickable" onclick="location.hash='group-${g}'">
      <div class="gc-head"><h3>Group ${g}</h3><span class="gc-go">predicted vs actual →</span></div>
      <table class="gtable">
        <thead><tr><th></th><th>Team (actual)</th><th>W-D-L</th><th>GF:GA</th><th>GD</th><th>Pts</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
  }).join('');
  $('groupsPanel').innerHTML = `
    <h2>📊 Group stage — final tables</h2>
    <p class="hint">The real 2026 group tables. <span class="tag tag-adv">advanced</span> reached the
      round of 32. Click a group to see our prediction beside reality, match by match.</p>
    ${pills(null)}
    <div class="groups-grid" style="margin-top:14px">${cards}</div>`;
}

const scoreCell = (arr, cls) => arr
  ? `<span class="sc ${cls}">${arr[0]}–${arr[1]}</span>` : `<span class="sc sc-pending">·</span>`;

function matchRow(mm) {
  const done = !!mm.actual;
  let badge = '<span class="badge badge-pending">upcoming</span>';
  if (done) {
    badge = mm.exact_hit ? '<span class="badge badge-exact">exact ✓✓</span>'
      : mm.outcome_hit ? '<span class="badge badge-ok">outcome ✓</span>'
        : '<span class="badge badge-miss">miss ✗</span>';
  }
  return `<div class="cmp-row ${done ? '' : 'is-pending'}">
    <span class="cmp-home">${mm.home}</span>
    <span class="cmp-scores">${scoreCell(mm.pred, 'sc-pred')}<span class="sc-vs">→</span>${scoreCell(mm.actual, 'sc-real')}</span>
    <span class="cmp-away">${mm.away}</span>${badge}</div>`;
}

function miniTable(rows, advSet, isActual) {
  return `<table class="cmp-table">
    <thead><tr><th></th><th>${isActual ? 'Actual' : 'Predicted'}</th><th>Pts</th><th>GD</th></tr></thead>
    <tbody>${rows.map((r, i) => `<tr class="${i < 2 ? 'row-top2' : ''} ${advSet.has(r.team) ? 'row-adv' : ''}">
      <td class="rk">${i + 1}</td><td class="tn">${r.team}${advSet.has(r.team) ? ' <span class="tag tag-adv">adv</span>' : ''}</td>
      <td><b>${r.pts}</b></td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td></tr>`).join('')}</tbody></table>`;
}

function renderGroupDetail(g) {
  const blk = A.groups[g];
  const advSet = new Set(A.advancers.actual);
  const predAdv = new Set(A.advancers.predicted);
  $('groupsPanel').innerHTML = `
    <button class="grp-back" onclick="location.hash='groups'">← All groups</button>
    ${pills(g)}
    <div class="grp-title" style="margin-top:12px">Group ${g}</div>
    <div class="cmp-tables" style="max-width:760px">
      <div class="cmp-col"><div class="cmp-cap cap-pred">Predicted</div>${miniTable(blk.pred_table, predAdv, false)}</div>
      <div class="cmp-col"><div class="cmp-cap cap-real">Actual</div>${miniTable(blk.actual_table, advSet, true)}</div>
    </div>
    <h3 style="margin-top:18px">All six matches — our score → real score</h3>
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

load().catch((e) => ($('err').textContent = 'Error: ' + e.message));
