const $ = (id) => document.getElementById(id);

async function load() {
  const r = await fetch('/actual.json');
  if (!r.ok) throw new Error(`actual.json HTTP ${r.status}`);
  const A = await r.json();
  $('asof').textContent = `results through ${A.as_of}`;
  renderStats(A.metrics);
  renderChamp(A.metrics);
  renderGroups(A);
  renderKnockout(A.knockout);
  requestAnimationFrame(animate);
}

const pctTxt = (x) => (x * 100).toFixed(0) + '%';

function tile(emoji, big, label, sub, tone) {
  return `<div class="tile tile-${tone} reveal">
    <div class="tile-emoji">${emoji}</div>
    <div class="tile-big" data-count="${big.n ?? ''}">${big.txt}</div>
    <div class="tile-label">${label}</div>
    <div class="tile-sub">${sub}</div>
  </div>`;
}

function renderStats(m) {
  const beat = m.rps < m.rps_baserate;
  $('stats').innerHTML =
    tile('🎯', { txt: pctTxt(m.outcome_acc), n: m.outcome_acc * 100 },
         'Outcome accuracy', `${Math.round(m.outcome_acc * m.group_matches_scored)}/${m.group_matches_scored} W/D/L correct`, 'violet') +
    tile('🔢', { txt: pctTxt(m.exact_acc), n: m.exact_acc * 100 },
         'Exact scoreline', `${Math.round(m.exact_acc * m.group_matches_scored)}/${m.group_matches_scored} spot-on`, 'sky') +
    tile('📈', { txt: m.rps.toFixed(3) },
         'RPS on real games', `${beat ? 'beats' : 'vs'} base-rate ${m.rps_baserate.toFixed(3)} ${beat ? '✓' : ''}`, 'teal') +
    tile('🎟️', { txt: `${m.advancers_correct}/${m.advancers_total}`, n: m.advancers_correct },
         'Qualifiers called', `plus ${m.top2_correct}/${m.top2_total} group top-2`, 'amber') +
    tile(m.champion_alive ? '💚' : '💔', { txt: m.champion_alive ? 'Alive' : 'Out' },
         'Predicted champion', m.champion, m.champion_alive ? 'green' : 'coral');
}

function renderChamp(m) {
  $('champ').innerHTML = `<p class="champ-line">Our pre-tournament pick <b>${m.champion}</b> is
    ${m.champion_alive
      ? '<span class="alive">still in the tournament</span> 💚'
      : '<span class="dead">already eliminated</span> 💔'}.
    Across the 12 groups we correctly placed <b>${m.top2_correct}/${m.top2_total}</b> of the
    top-two spots and <b>${m.advancers_correct}/${m.advancers_total}</b> of the eventual round-of-32 teams.</p>`;
}

const scoreCell = (arr, cls) => arr
  ? `<span class="sc ${cls}">${arr[0]}–${arr[1]}</span>`
  : `<span class="sc sc-pending">·</span>`;

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
    <span class="cmp-away">${mm.away}</span>
    ${badge}
  </div>`;
}

function miniTable(rows, advSet, isActual) {
  return `<table class="cmp-table">
    <thead><tr><th></th><th>${isActual ? 'Actual' : 'Predicted'}</th><th>Pts</th><th>GD</th></tr></thead>
    <tbody>${rows.map((r, i) => {
      const adv = advSet.has(r.team);
      return `<tr class="${i < 2 ? 'row-top2' : ''} ${adv ? 'row-adv' : ''}">
        <td class="rk">${i + 1}</td>
        <td class="tn">${r.team}${adv ? ' <span class="tag tag-adv">adv</span>' : ''}</td>
        <td><b>${r.pts}</b></td><td>${r.gd > 0 ? '+' : ''}${r.gd}</td></tr>`;
    }).join('')}</tbody></table>`;
}

function renderGroups(A) {
  const advSet = new Set(A.advancers.actual);
  const predAdv = new Set(A.advancers.predicted);
  $('groups').innerHTML = Object.entries(A.groups).map(([g, blk]) => `
    <div class="gcard reveal">
      <h3>Group ${g}</h3>
      <div class="cmp-tables">
        <div class="cmp-col"><div class="cmp-cap cap-pred">Predicted</div>
          ${miniTable(blk.pred_table, predAdv, false)}</div>
        <div class="cmp-col"><div class="cmp-cap cap-real">Actual</div>
          ${miniTable(blk.actual_table, advSet, true)}</div>
      </div>
      <div class="cmp-matches">${blk.matches.map(matchRow).join('')}</div>
    </div>`).join('');
}

function renderKnockout(ko) {
  if (!ko || !ko.length) { $('koSec').style.display = 'none'; return; }
  $('knockout').innerHTML = `<div class="ko-list">` + ko.map((mm) => {
    const done = !!mm.actual;
    return `<div class="cmp-row ko-row ${done ? '' : 'is-pending'}">
      <span class="cmp-home">${mm.home}</span>
      <span class="cmp-scores">${scoreCell(mm.actual, 'sc-real')}</span>
      <span class="cmp-away">${mm.away}</span>
      ${mm.we_predicted_this_tie ? '<span class="badge badge-ok">on our bracket ✓</span>'
        : '<span class="badge badge-pending">—</span>'}
    </div>`;
  }).join('') + `</div>`;
}

// count-up on the percentage stat tiles (containers fade in via CSS)
function animate() {
  document.querySelectorAll('.tile-big[data-count]').forEach((el) => {
    const target = parseFloat(el.dataset.count);
    if (!el.dataset.count || !isFinite(target)) return;
    if (!el.textContent.trim().endsWith('%')) return;        // only animate % tiles
    const dur = 800;
    let t0 = null;
    const tick = (ts) => {
      t0 = t0 ?? ts;
      const k = Math.min((ts - t0) / dur, 1);
      const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(target * eased) + '%';
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

load().catch((e) => ($('err').textContent = 'Error: ' + e.message));
