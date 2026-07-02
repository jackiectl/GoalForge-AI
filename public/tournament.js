const $ = (id) => document.getElementById(id);
let T, GROUPS;

async function load() {
  const r = await fetch('/tournament.json');
  if (!r.ok) throw new Error(`tournament.json HTTP ${r.status}`);
  T = await r.json();
  GROUPS = Object.keys(T.groups).sort();
  document.querySelectorAll('.viewtab').forEach((b) => {
    b.onclick = () => { location.hash = b.dataset.view === 'bracket' ? 'bracket' : 'groups'; };
  });
  window.addEventListener('hashchange', route);
  route();
}

function route() {
  const h = location.hash.slice(1);
  if (h === 'bracket') return showBracket();
  if (h.startsWith('group-') && T.groups[h.slice(6)]) return showGroups(h.slice(6));
  return showGroups(null);
}

const setTab = (v) => document.querySelectorAll('.viewtab')
  .forEach((b) => b.classList.toggle('active', b.dataset.view === v));

function showBracket() {
  setTab('bracket');
  $('view-groups').hidden = true;
  $('view-bracket').hidden = false;
  const byMid = {};
  for (const rnd of ['r32', 'r16', 'qf', 'sf', 'third_place', 'final']) {
    const arr = T.bracket[rnd];
    if (!Array.isArray(arr)) continue;
    for (const m of arr) if (m.id) byMid[m.id] = { home: m.home, away: m.away,
      hs: m.reg ? m.reg[0] : m.hg, as: m.reg ? m.reg[1] : m.ag,
      winner: m.winner, pens: m.pens, decided: m.decided };
  }
  renderBracket($('bracket'), byMid, { champion: T.bracket.champion, championLabel: 'Predicted champion' });
}

function showGroups(g) {
  setTab('groups');
  $('view-bracket').hidden = true;
  $('view-groups').hidden = false;
  g ? renderGroupDetail(g) : renderOverview();
}

const pills = (active) => `<div class="gsel"><span class="gsel-lbl">Group</span>` +
  GROUPS.map((g) => `<button class="gpill ${g === active ? 'active' : ''}"
    onclick="location.hash='group-${g}'">${g}</button>`).join('') +
  (active ? `<button class="gpill" onclick="location.hash='groups'">All ▸</button>` : '') + `</div>`;

const gdRow = (r, i, advSet) => {
  const cls = i < 2 ? 'adv' : (i === 2 && advSet.has(r.team) ? 'third-adv' : '');
  return `<tr class="${cls}"><td>${i + 1}</td><td class="tname">${r.team}</td>
    <td>${r.w}-${r.d}-${r.l}</td><td>${r.gf}:${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
    <td><b>${r.pts}</b></td><td class="mut">${r.xpts.toFixed(1)}</td></tr>`;
};

function renderOverview() {
  const advSet = new Set(T.thirds.advanced);
  const cards = GROUPS.map((g) => {
    const rows = T.groups[g].table.map((r, i) => gdRow(r, i, advSet)).join('');
    return `<div class="gcard clickable" onclick="location.hash='group-${g}'">
      <div class="gc-head"><h3>Group ${g}</h3><span class="gc-go">details →</span></div>
      <table class="gtable">
        <thead><tr><th></th><th>Team</th><th>W-D-L</th><th>GF:GA</th><th>GD</th><th>Pts</th><th class="mut">xPts</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
  }).join('');
  const thirds = T.thirds.ranking.map((t, i) =>
    `<span class="chip ${advSet.has(t.team) ? 'chip-adv' : 'chip-out'}"
       title="pts ${t.pts} · gd ${t.gd} · gf ${t.gf}">${i + 1}. ${t.team} <em>(${t.group})</em></span>`).join('');
  $('groupsPanel').innerHTML = `
    <h2>📊 Group stage — all 12 groups</h2>
    <p class="hint">Most likely score per match; standings use the official 2026 tiebreakers
      (head-to-head first). <b>xPts</b> = expected points over all outcomes.
      <span class="adv-key">■ top two advance</span> <span class="third-key">■ third (may advance)</span>.
      Click a group for all six matches.</p>
    ${pills(null)}
    <div class="groups-grid" style="margin-top:14px">${cards}</div>
    <h3 style="margin-top:22px">Third-place ranking — 8 of 12 advance</h3>
    <div class="thirds-row">${thirds}</div>`;
}

function mcardPred(m) {
  const pct = (x) => (x * 100).toFixed(0) + '%';
  const ph = (m.p_home * 100).toFixed(0), pd = (m.p_draw * 100).toFixed(0), pa = (m.p_away * 100).toFixed(0);
  return `<div class="mcard">
    <div class="mcard-row">
      <span class="mc-team h">${m.home}</span>
      <span class="mc-score sc-pred">${m.hg}–${m.ag}</span>
      <span class="mc-team a">${m.away}</span>
    </div>
    <div class="mc-prob"><i class="ph" style="width:${ph}%"></i><i class="pd" style="width:${pd}%"></i><i class="pa" style="width:${pa}%"></i></div>
    <div class="mc-plabels"><span>${pct(m.p_home)} win</span><span>${pct(m.p_draw)} draw</span><span>${pct(m.p_away)} win</span></div>
  </div>`;
}

function renderGroupDetail(g) {
  const blk = T.groups[g];
  const advSet = new Set(T.thirds.advanced);
  const standings = blk.table.map((r, i) => {
    const cls = i < 2 ? 'adv' : (i === 2 && advSet.has(r.team) ? 'third-adv' : '');
    return `<tr class="${cls}"><td class="s-rank">${i + 1}</td><td class="s-team">${r.team}</td>
      <td>${r.w}-${r.d}-${r.l}</td><td>${r.gf}:${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
      <td class="s-pts">${r.pts}</td><td class="mut">${r.xpts.toFixed(1)}</td></tr>`;
  }).join('');
  $('groupsPanel').innerHTML = `
    <button class="grp-back" onclick="location.hash='groups'">← All groups</button>
    ${pills(g)}
    <div class="grp-detail" style="margin-top:14px">
      <div>
        <div class="grp-title">Group ${g}</div>
        <table class="standings">
          <thead><tr><th></th><th>Team</th><th>W-D-L</th><th>GF:GA</th><th>GD</th><th>Pts</th><th>xPts</th></tr></thead>
          <tbody>${standings}</tbody></table>
        <p class="hint">▲ predicted to advance to the round of 32.</p>
      </div>
      <div>
        <h3>All six matches — predicted</h3>
        <div class="match-grid">${blk.matches.map(mcardPred).join('')}</div>
      </div>
    </div>`;
}

load().catch((e) => ($('err').textContent = 'Error: ' + e.message));
