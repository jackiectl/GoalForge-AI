const $ = (id) => document.getElementById(id);

async function load() {
  const r = await fetch('/live.json');
  if (!r.ok) throw new Error(`live.json HTTP ${r.status}`);
  const L = await r.json();
  $('asof').textContent = `through ${L.as_of}`;
  $('asof2').textContent = L.as_of;
  renderChamps(L);
  renderOdds(L);
  renderBracket($('bracket'), L.bracket, { champion: L.champion_live, championLabel: 'Live champion' });
  renderExplain(L);
}

function renderChamps(L) {
  const same = L.champion_live === L.champion_original;
  $('champs').innerHTML =
    `<div class="tile tile-sky" style="grid-column:span 2">
       <div class="tile-emoji">🧊</div><div class="tile-big">${L.champion_original}</div>
       <div class="tile-label">Original pick — frozen at kick-off</div>
       <div class="tile-sub">never sees a 2026 result</div></div>
     <div class="tile tile-violet" style="grid-column:span 2">
       <div class="tile-emoji">🔄</div><div class="tile-big">${L.champion_live}</div>
       <div class="tile-label">Live pick — refit through ${L.as_of}</div>
       <div class="tile-sub">real results + re-projected bracket</div></div>
     <div class="tile ${same ? 'tile-green' : 'tile-amber'}">
       <div class="tile-emoji">${same ? '🤝' : '↔️'}</div>
       <div class="tile-big" style="font-size:22px">${same ? 'Agree' : 'Differ'}</div>
       <div class="tile-label">${same ? 'Both still back' : 'The update moved'}</div>
       <div class="tile-sub">${same ? L.champion_live : `${L.champion_original} → ${L.champion_live}`}</div></div>`;
}

function renderOdds(L) {
  const odds = L.original_odds || [];
  const max = Math.max(...odds.map((o) => o.p), 0.01);
  $('odds').innerHTML = odds.map((o) =>
    `<div class="bar"><span class="lbl">${o.team}</span>
      <span class="track"><span class="fill" style="width:${(o.p / max * 100).toFixed(0)}%"></span></span>
      <span class="pct">${(o.p * 100).toFixed(0)}%</span></div>`).join('');
}

function renderExplain(L) {
  // find teams whose live knockout run differs notably: reached SF/final in live
  const b = L.bracket;
  const win = (id) => (b[id] || {}).winner;
  const finalists = [win('M101'), win('M102')].filter(Boolean);
  const predRuns = Object.values(b).filter((m) => m.pred && m.decided === 'pens').length;
  $('explain').innerHTML = `<p>Both models share the same player layer and Dixon-Coles machinery;
    the difference is <b>information</b>. The original is a true pre-tournament forecast — it was
    fit only on data before 2026-06-11 and predicts its own bracket from predicted qualifiers. The
    <b>live</b> model is refit on every international match through <b>${L.as_of}</b>, so team
    ratings now carry 2026 form, and it walks the <b>real</b> bracket — the actual qualifiers and
    round-of-32 pairings — using real results where they exist.</p>
    <p>Right now the live projection has <b>${finalists.join(' vs ') || 'its finalists'}</b> reaching
    the final and <b>${L.champion_live}</b> lifting the trophy${L.champion_live === L.champion_original
      ? ', agreeing with the frozen pick' : `, a change from the frozen pick of ${L.champion_original}`}.
    ${predRuns} of the projected ties are coin-flip shootouts. As more games are played, re-running
    the daily refresh will keep re-drawing this bracket from reality.</p>`;
}

load().catch((e) => ($('err').textContent = 'Error: ' + e.message));
