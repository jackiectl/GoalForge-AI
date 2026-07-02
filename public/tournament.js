const $ = (id) => document.getElementById(id);

async function load() {
  const r = await fetch('/tournament.json');
  if (!r.ok) throw new Error(`tournament.json HTTP ${r.status}`);
  const T = await r.json();
  renderGroups(T);
  renderThirds(T);
  renderBracket(T);
}

const flagRow = (m) => {
  const pct = (x) => (x * 100).toFixed(0) + '%';
  const title = `P(${m.home}) ${pct(m.p_home)} · draw ${pct(m.p_draw)} · P(${m.away}) ${pct(m.p_away)}`;
  return `<div class="mrow" title="${title}">
    <span class="mteam h">${m.home}</span>
    <span class="mscore">${m.hg}–${m.ag}</span>
    <span class="mteam a">${m.away}</span>
  </div>`;
};

function renderGroups(T) {
  const advanced = new Set(T.thirds.advanced);
  $('groups').innerHTML = Object.entries(T.groups).map(([g, blk]) => {
    const rows = blk.table.map((r, i) => {
      const cls = i < 2 ? 'adv' : (i === 2 && advanced.has(r.team) ? 'third-adv' : (i === 2 ? 'third' : ''));
      return `<tr class="${cls}"><td>${i + 1}</td><td class="tname">${r.team}</td>
        <td>${r.w}-${r.d}-${r.l}</td><td>${r.gf}:${r.ga}</td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td>
        <td><b>${r.pts}</b></td><td class="mut">${r.xpts.toFixed(1)}</td></tr>`;
    }).join('');
    return `<div class="gcard">
      <h3>Group ${g}</h3>
      <table class="gtable">
        <thead><tr><th></th><th>Team</th><th>W-D-L</th><th>GF:GA</th><th>GD</th><th>Pts</th><th class="mut">xPts</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="gmatches">${blk.matches.map(flagRow).join('')}</div>
    </div>`;
  }).join('');
}

function renderThirds(T) {
  const adv = new Set(T.thirds.advanced);
  $('thirds').innerHTML = `<div class="thirds-row">` + T.thirds.ranking.map((t, i) =>
    `<span class="chip ${adv.has(t.team) ? 'chip-adv' : 'chip-out'}"
       title="pts ${t.pts} · gd ${t.gd} · gf ${t.gf}">${i + 1}. ${t.team} <em>(${t.group})</em></span>`
  ).join('') + `</div>`;
}

const ROUND_LABEL = { r32: 'Round of 32', r16: 'Round of 16', qf: 'Quarter-finals',
                     sf: 'Semi-finals', third_place: 'Third place', final: 'Final' };

function renderBracket(T) {
  const b = T.bracket;
  const koRow = (m) => {
    const et = m.decided === 'et_pens';
    const pct = (m.p_win * 100).toFixed(0);
    return `<div class="krow" title="P(${m.winner} advances) ${pct}%">
      <span class="mteam h ${m.winner === m.home ? 'kwin' : ''}">${m.home}</span>
      <span class="mscore">${m.hg}–${m.ag}${et ? '*' : ''}</span>
      <span class="mteam a ${m.winner === m.away ? 'kwin' : ''}">${m.away}</span>
      <span class="kid mut">${m.id}</span>
    </div>`;
  };
  $('bracket').innerHTML =
    ['r32', 'r16', 'qf', 'sf', 'third_place', 'final'].map((rnd) =>
      `<div class="kround"><h3>${ROUND_LABEL[rnd]}</h3>${(b[rnd] || []).map(koRow).join('')}</div>`
    ).join('') +
    `<div class="champ">🏆 Predicted champion: <b>${b.champion}</b></div>
     <p class="hint">* most-likely score is a draw after 90 minutes — the likelier side is
       advanced (extra time / penalties).</p>`;
}

load().catch((e) => ($('err').textContent = 'Error: ' + e.message));
