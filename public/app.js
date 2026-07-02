const $ = (id) => document.getElementById(id);
const t = window.t || ((s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s));

let META = {};
let HOSTS = new Set();
const isHost = (t) => HOSTS.has(t);

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

async function init() {
  const { teams, meta } = await api('/api/teams');
  META = meta || {};
  HOSTS = new Set(META.hosts || []);
  const opts = teams.map((t) => `<option>${t}</option>`).join('');
  $('home').innerHTML = opts;
  $('away').innerHTML = opts;
  $('away').selectedIndex = Math.min(1, teams.length - 1);
  updateVenue();
  await Promise.all([loadXI('home'), loadXI('away')]);
  $('home').onchange = () => { updateVenue(); loadXI('home'); };
  $('away').onchange = () => { updateVenue(); loadXI('away'); };
  $('neutral').onchange = renderVenueNote;
  $('go').onclick = predict;
  renderMethod();
  renderForecast();
}

// --- venue: neutral by default; a single 2026 host gets home advantage ---------------
function updateVenue() {
  const oneHost = isHost($('home').value) !== isHost($('away').value); // XOR
  $('neutral').checked = !oneHost;
  renderVenueNote();
}

function renderVenueNote() {
  const h = $('home').value, a = $('away').value;
  if ($('neutral').checked) {
    $('venueNote').textContent = t('Neutral venue — World Cup default (no home advantage).');
  } else {
    const host = isHost(h) ? h : isHost(a) ? a : h;
    $('venueNote').textContent = isHost(host)
      ? '🏠 ' + t('Home advantage: {host} (2026 host)', { host })
      : '🏠 ' + t('Home advantage: {host}', { host });
  }
}

async function loadXI(side) {
  const team = $(side).value;
  $(side === 'home' ? 'homeName' : 'awayName').textContent = team;
  const { players, default_xi, info } = await api(`/api/squad?team=${encodeURIComponent(team)}`);
  const def = new Set(default_xi);
  const row = (p) => {
    const i = info && info[p];
    const xa = i && i.club_xa != null ? ` · xA ${i.club_xa}` : '';
    const meta = i && i.caps != null
      ? `<span class="pmeta">${i.pos || ''} · ${t('{n} caps', { n: i.caps })} · ${t('{n} gls', { n: i.goals })}${xa}</span>` : '';
    return `<label><input type="checkbox" value="${p}" ${def.has(p) ? 'checked' : ''}/>
      <span class="pname">${p}</span>${meta}</label>`;
  };
  const starters = players.slice(0, 11).map(row).join('');
  const bench = players.slice(11).map(row).join('');
  $(side === 'home' ? 'homeXI' : 'awayXI').innerHTML =
    starters + (bench ? `<div class="benchsep">${t('Bench')}</div>${bench}` : '');
}

const xiOf = (side) =>
  [...document.querySelectorAll(`#${side === 'home' ? 'homeXI' : 'awayXI'} input:checked`)].map((i) => i.value);

const pct = (x) => (x * 100).toFixed(0) + '%';

function bars(el, arr) {
  el.innerHTML = arr
    .map((o) => `<div class="bar"><span class="lbl">${o.player}</span>
      <span class="track"><span class="fill" style="width:${(o.prob * 100).toFixed(0)}%"></span></span>
      <span class="pct">${pct(o.prob)}</span></div>`)
    .join('');
}

let lastPrediction = null;

async function predict() {
  $('err').textContent = '';
  $('go').disabled = true;
  $('go').textContent = t('Simulating…');
  try {
    let homeTeam = $('home').value, awayTeam = $('away').value;
    let homeXI = xiOf('home'), awayXI = xiOf('away');
    const neutral = $('neutral').checked;
    // If not neutral, the advantaged (home) side must be the host — reorder if the host was picked as away.
    if (!neutral && isHost(awayTeam) && !isHost(homeTeam)) {
      [homeTeam, awayTeam] = [awayTeam, homeTeam];
      [homeXI, awayXI] = [awayXI, homeXI];
    }
    const p = await api('/api/predict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ home_team: homeTeam, away_team: awayTeam,
        home_xi: homeXI, away_xi: awayXI, neutral }),
    });
    lastPrediction = p;
    renderResult();
  } catch (e) {
    $('err').textContent = t('Error: {msg}', { msg: e.message });
  } finally {
    $('go').disabled = false;
    $('go').textContent = t('Predict');
  }
}

// Render the match result from the last prediction; re-runs on language toggle (no re-fetch).
function renderResult() {
  const p = lastPrediction;
  if (!p) return;
  $('results').classList.remove('hidden');
  $('matchTitle').textContent = `${p.home_team} vs ${p.away_team}`;
  const rows = [
    [p.home_team, p.prob_home], [t('Draw'), p.prob_draw], [p.away_team, p.prob_away],
  ];
  $('outcome').innerHTML = rows
    .map(([n, v]) => `<div class="obar"><span class="oname">${n}</span>
      <span class="track"><span class="fill" style="width:${(v * 100).toFixed(0)}%"></span></span>
      <span class="pct">${pct(v)}</span></div>`)
    .join('');
  const score = `${p.projected_score[0]}–${p.projected_score[1]}`;
  const eg = `${p.exp_home_goals.toFixed(2)}–${p.exp_away_goals.toFixed(2)}`;
  const likely = p.top_scores.map((s) => `${s.home}-${s.away} ${pct(s.prob)}`).join(', ');
  $('score').innerHTML =
    t('<b>{score}</b> projected · expected goals {eg} · most likely exact: {likely}', { score, eg, likely });
  $('hsTitle').textContent = t('{team} — scorers', { team: p.home_team });
  $('asTitle').textContent = t('{team} — scorers', { team: p.away_team });
  $('haTitle').textContent = t('{team} — assisters', { team: p.home_team });
  $('aaTitle').textContent = t('{team} — assisters', { team: p.away_team });
  bars($('homeScorers'), p.home_scorers);
  bars($('awayScorers'), p.away_scorers);
  bars($('homeAssists'), p.home_assisters);
  bars($('awayAssists'), p.away_assisters);
}

document.addEventListener('gf:langchange', renderResult);

function renderMethod() {
  const m = META.method || {}, b = META.backtest || {};
  const li = (k, v) => (v ? `<li><b>${k}:</b> ${v}</li>` : '');
  $('methodBody').innerHTML =
    '<ul>' +
    li(t('Scoreline'), m.scoreline) + li(t('Scorers'), m.scorer) + li(t('Assists'), m.assist) +
    li(t('Default XI'), m.default_xi) + li(t('Venue'), m.venue) + '</ul>' +
    (b.test_rps ? `<p class="mnote">` + t('Team layer held-out backtest on international matches: RPS {rps} (lower is better — beats Elo &amp; base-rate). The scorer &amp; assist layers are history/prior-based and are <b>not</b> validated on 2026 outcomes.', { rps: b.test_rps }) + `</p>` : '') +
    (META.note ? `<p class="mnote">${META.note}</p>` : '');
}

async function renderForecast() {
  if (!$('forecast')) return;                                  // page without the forecast section
  let f;
  try { f = await api('/forecast.json'); } catch { return; }   // not deployed yet -> skip quietly
  $('forecast').classList.remove('hidden');
  $('fcMeta').textContent = t('· {n}k sims · ~{g} goals', { n: Math.round(f.sims / 1000), g: Math.round(f.exp_total_goals) });
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

init().catch((e) => ($('err').textContent = t('Init error: {msg}', { msg: e.message })));
