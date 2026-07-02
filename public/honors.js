const $ = (id) => document.getElementById(id);

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} HTTP ${r.status}`);
  return r.json();
}

function boardTable(el, rows, unit) {
  el.innerHTML = `<thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th>
      <th class="num">${unit}</th></tr></thead><tbody>` +
    rows.slice(0, 15).map((r, i) =>
      `<tr><td>${i + 1}</td><td>${r.player}</td><td class="mut">${r.team}</td>
       <td class="mut">${r.pos}</td><td class="num"><b>${r.exp.toFixed(2)}</b></td></tr>`).join('') +
    '</tbody>';
}

async function renderPath() {
  const T = await getJSON('/tournament.json');
  const h = T.honors;
  $('pathMeta').textContent = `· ${h.total_goals} goals on the modal path`;
  boardTable($('bootTable'), h.golden_boot, 'xG');
  boardTable($('playTable'), h.playmaker, 'xA');
  if (h.golden_glove) {
    const g = h.golden_glove;
    $('glove').innerHTML = `🧤 <b>Golden Glove pick:</b> ${g.player} (${g.team}) — deepest-run
      defence, ${g.conceded} goals conceded in ${g.matches} predicted matches
      (${g.per_match}/match).`;
  }
}

async function renderForecast() {
  const f = await getJSON('/forecast.json');
  $('fcMeta').textContent = `· ${Math.round(f.sims / 1000)}k sims · ~${Math.round(f.exp_total_goals)} goals`;
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

Promise.allSettled([renderPath(), renderForecast()]).then((rs) => {
  const bad = rs.filter((r) => r.status === 'rejected');
  if (bad.length) $('err').textContent = 'Error: ' + bad.map((b) => b.reason.message).join(' · ');
});
