/* GoalForge Prediction Game — a virtual-Coin knockout game. No real money.
   State lives in localStorage; odds are computed client-side from public/odds.json with the same
   Dixon-Coles + GBM ensemble blend the site's API uses; bets settle against public/actual.json. */
const $ = (id) => document.getElementById(id);
const t = window.t || ((s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s));
const INIT = 1000;
const STORE = 'gf_game_v1';

const ROUNDS = [
  { key: 'r32', name: 'Round of 32', emoji: '⚔️', mids: Array.from({ length: 16 }, (_, i) => 'M' + (73 + i)) },
  { key: 'r16', name: 'Round of 16', emoji: '🔥', mids: ['M89', 'M90', 'M91', 'M92', 'M93', 'M94', 'M95', 'M96'] },
  { key: 'qf', name: 'Quarter-finals', emoji: '💥', mids: ['M97', 'M98', 'M99', 'M100'] },
  { key: 'sf', name: 'Semi-finals', emoji: '🌟', mids: ['M101', 'M102'] },
  { key: 'final', name: 'Final', emoji: '🏆', mids: ['M104'] },
];
const QUOTA = { r32: 4, r16: 3, qf: 2, sf: 1, final: 1 };
const ENTRY_IDX = { r32: 0, r16: 1, qf: 2, sf: 3, final: 4 };
const midIdx = {};
ROUNDS.forEach((r, ri) => r.mids.forEach((m) => (midIdx[m] = ri)));

let M, A, S;

function loadState() {
  try { S = JSON.parse(localStorage.getItem(STORE)); } catch (e) { S = null; }
  if (!S || typeof S !== 'object') S = { entryRound: 'r32', bets: {} };
  S.bets = S.bets || {};
  S.entryRound = S.entryRound || 'r32';
}
const save = () => localStorage.setItem(STORE, JSON.stringify(S));

/* ---------- odds engine: neutral Dixon-Coles + 50/50 GBM blend (see api/_engine.py) ---------- */
function pois(k, l) { let f = 1; for (let i = 2; i <= k; i++) f *= i; return Math.exp(-l) * Math.pow(l, k) / f; }
function grid(h, a) {
  const K = 10, rho = M.rho || 0;
  const lh = Math.exp(M.mu + (M.attack[h] || 0) + (M.defence[a] || 0));
  const la = Math.exp(M.mu + (M.attack[a] || 0) + (M.defence[h] || 0));
  const g = [];
  for (let i = 0; i <= K; i++) { g[i] = []; for (let j = 0; j <= K; j++) g[i][j] = pois(i, lh) * pois(j, la); }
  g[0][0] *= 1 - lh * la * rho; g[0][1] *= 1 + lh * rho; g[1][0] *= 1 + la * rho; g[1][1] *= 1 - rho;
  let t = 0; for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) t += g[i][j];
  for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) g[i][j] /= t;
  return { g, K };
}
function outcome(h, a) {
  const { g, K } = grid(h, a); let ph = 0, pd = 0, pa = 0;
  for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) {
    if (i > j) ph += g[i][j]; else if (i === j) pd += g[i][j]; else pa += g[i][j];
  }
  const e = M.ens, key = h + '|' + a + '|0';
  if (e && e.probs && e.probs[key]) {
    const pg = e.probs[key], w = (e.w == null ? 0.5 : e.w);
    const p = [w * ph + (1 - w) * pg[0], w * pd + (1 - w) * pg[1], w * pa + (1 - w) * pg[2]];
    const s = p[0] + p[1] + p[2];
    return { ph: p[0] / s, pd: p[1] / s, pa: p[2] / s };
  }
  return { ph, pd, pa };
}
function advProb(h, a) { const { ph, pa } = outcome(h, a); return ph / (ph + pa); }   // P(home advances)
function scoreProb(h, a, i, j) { const { g, K } = grid(h, a); return (i >= 0 && j >= 0 && i <= K && j <= K) ? Math.max(g[i][j], 1e-6) : 1e-6; }
const dec = (p) => Math.max(1.01, 1 / Math.max(p, 1e-6));       // fair decimal odds
const tieOdds = (h, a) => { const p = advProb(h, a); return { ph: p, pa: 1 - p, oh: dec(p), oa: dec(1 - p) }; };

/* ---------- settlement against the real bracket ---------- */
function settleBet(mid, bet) {
  const m = A.bracket[mid];
  if (!m || !m.played) return { status: 'pending', payout: 0 };
  if (bet.pick !== m.winner) return { status: 'lost', payout: 0 };
  const reg = m.reg || m.actual;
  if (bet.score && reg && reg[0] === bet.score[0] && reg[1] === bet.score[1])
    return { status: 'exact', payout: bet.stake * bet.sOdds };
  return { status: 'outcome', payout: bet.stake * bet.wOdds };
}
function bankroll() {
  let b = INIT;
  for (const mid in S.bets) { const bet = S.bets[mid]; b -= bet.stake; b += settleBet(mid, bet).payout; }
  return b;
}
function baseline() {                                            // the model backs its pick, flat 100, every tie
  let b = INIT, settled = 0;
  for (const r of ROUNDS) for (const mid of r.mids) {
    const m = A.bracket[mid];
    if (!m || !m.home || !m.away || !m.played) continue;
    const p = advProb(m.home, m.away), pick = p >= 0.5 ? m.home : m.away, stake = 100;
    b -= stake; if (m.winner === pick) b += stake * dec(Math.max(p, 1 - p)); settled++;
  }
  return { coins: b, settled };
}

/* ---------- rendering ---------- */
const fmt = (x) => Math.round(x).toLocaleString();
const slotsTotal = () => QUOTA[S.entryRound];
const slotsUsed = () => Object.keys(S.bets).length;

function realLine(m) {
  const reg = m.reg || m.actual || [];
  let s = `${m.home} ${reg[0]}–${reg[1]} ${m.away}`;
  if (m.decided === 'pens' && m.pens) s += ` <span class="gm-pk">(${t('pens {a}–{b}', { a: m.pens[0], b: m.pens[1] })})</span>`;
  return s + ` → <b>${m.winner}</b>`;
}

function renderWallet() {
  const bk = bankroll(), used = slotsUsed(), tot = slotsTotal(), net = bk - INIT;
  let settled = 0;
  for (const mid in S.bets) if (settleBet(mid, S.bets[mid]).status !== 'pending') settled++;
  $('wallet').innerHTML = `
    <div class="tile tile-violet"><div class="tile-emoji">💰</div><div class="tile-big">${fmt(bk)}</div>
      <div class="tile-label">Coins</div><div class="tile-sub">${t('started with {n}', { n: fmt(INIT) })}</div></div>
    <div class="tile tile-sky"><div class="tile-emoji">🎟️</div><div class="tile-big">${used}/${tot}</div>
      <div class="tile-label">${t('Calls used')}</div><div class="tile-sub">${t('{n} left', { n: tot - used })}</div></div>
    <div class="tile tile-green"><div class="tile-emoji">✅</div><div class="tile-big">${settled}</div>
      <div class="tile-label">${t('Settled')}</div><div class="tile-sub">${t('{n} pending', { n: used - settled })}</div></div>
    <div class="tile ${net >= 0 ? 'tile-green' : 'tile-amber'}"><div class="tile-emoji">${net >= 0 ? '📈' : '📉'}</div>
      <div class="tile-big">${net >= 0 ? '+' : ''}${fmt(net)}</div><div class="tile-label">${t('Net P/L')}</div>
      <div class="tile-sub">${t('vs start')}</div></div>`;
}

function renderBoard() {
  const you = bankroll(), bot = baseline();
  const rows = [
    { who: `🧑 ${t('You')}`, coins: you, sub: t('{n}/{m} calls placed', { n: slotsUsed(), m: slotsTotal() }) },
    { who: `🤖 ${t('Model')}`, coins: bot.coins, sub: t('backs its pick every tie · {n} settled', { n: bot.settled }) },
  ].sort((x, y) => y.coins - x.coins);
  $('board').innerHTML = rows.map((r, i) =>
    `<div class="gm-rank ${i === 0 ? 'gm-lead' : ''}">
       <span class="gm-medal">${i === 0 ? '👑' : '②'}</span>
       <span class="gm-who">${r.who}</span>
       <span class="gm-rsub">${r.sub}</span>
       <span class="gm-coins">${fmt(r.coins)} <small>Coins</small></span>
     </div>`).join('');
}

function tieCard(mid) {
  const m = A.bracket[mid] || {};
  const ri = midIdx[mid];
  const bettableRound = ri >= ENTRY_IDX[S.entryRound];
  const bet = S.bets[mid];
  const known = m.home && m.away;
  let body;

  if (bet) {
    const r = settleBet(mid, bet);
    const label = { pending: t('⏳ Pending'), outcome: t('✅ Won · outcome'), exact: t('🎯 Won · exact score!'), lost: t('❌ Lost') }[r.status];
    const cls = { pending: 'gm-pending', outcome: 'gm-won', exact: 'gm-won gm-exact', lost: 'gm-lost' }[r.status];
    const delta = r.payout ? ` · +${fmt(r.payout)}` : (r.status === 'lost' ? ` · −${fmt(bet.stake)}` : '');
    const line = bet.score
      ? t('Stake {n} · outcome ×{o} · score ×{s}', { n: fmt(bet.stake), o: bet.wOdds.toFixed(2), s: bet.sOdds.toFixed(1) })
      : t('Stake {n} · outcome ×{o}', { n: fmt(bet.stake), o: bet.wOdds.toFixed(2) });
    body = `<div class="gm-slip ${cls}">
        <div><b>${t('Backed:')}</b> ${t('{team} to advance', { team: bet.pick })}${bet.score ? ' · ' + t('exact {h}–{a}', { h: bet.score[0], a: bet.score[1] }) : ''}</div>
        <div class="gm-fine">${line}</div>
        <div class="gm-badge">${label}${delta}</div>
        ${m.played ? `<div class="gm-fine">${t('Real: {line}', { line: realLine(m) })}</div>` : ''}
        ${r.status === 'pending' ? `<button class="gm-mini" data-act="cancel" data-mid="${mid}">${t('Cancel (refund)')}</button>` : ''}
      </div>`;
  } else if (!known) {
    body = `<div class="gm-lock">🔒 ${t('Waiting on the teams for this tie')}</div>`;
  } else if (m.played) {
    const o = tieOdds(m.home, m.away), pick = o.ph >= 0.5 ? m.home : m.away;
    body = `<div class="gm-ref">${t('Already played — {line}', { line: realLine(m) })}
       <div class="gm-fine">${t('Model backed {team}', { team: `<b>${pick}</b>` })} ${m.winner === pick ? `<span class="tag tag-adv">${t('✓ hit')}</span>` : `<span class="tag gm-miss">${t('✗ miss')}</span>`}</div></div>`;
  } else if (!bettableRound) {
    const o = tieOdds(m.home, m.away);
    body = `<div class="gm-lock">${t('Before you joined · reference odds {a}% / {b}%', { a: (o.ph * 100).toFixed(0), b: (o.pa * 100).toFixed(0) })}</div>`;
  } else if (slotsUsed() >= slotsTotal()) {
    body = `<div class="gm-lock">${t('All {n} calls used — reset to play again', { n: slotsTotal() })}</div>`;
  } else {
    const o = tieOdds(m.home, m.away);
    body = `<div class="gm-form">
        <div class="gm-stakerow">
          <label class="gm-lbl">${t('Stake')}
            <input type="number" class="gm-stake" data-mid="${mid}" value="100" min="10" step="10"></label>
          <label class="gm-lbl">${t("Exact 120' score")} <span class="gm-opt">${t('(optional — pays more)')}</span>
            <span class="gm-scorein">
              <input type="number" class="gm-sh" data-mid="${mid}" min="0" max="9" placeholder="${m.home.slice(0, 3)}">
              <span class="gm-dash">–</span>
              <input type="number" class="gm-sa" data-mid="${mid}" min="0" max="9" placeholder="${m.away.slice(0, 3)}">
            </span></label>
        </div>
        <div class="gm-picks">
          <button class="gm-pick" data-act="bet" data-mid="${mid}" data-team="H">${t('Back {team}', { team: m.home })}
            <small>${t('advance {p}% · pays ×{o}', { p: (o.ph * 100).toFixed(0), o: o.oh.toFixed(2) })}</small></button>
          <button class="gm-pick" data-act="bet" data-mid="${mid}" data-team="A">${t('Back {team}', { team: m.away })}
            <small>${t('advance {p}% · pays ×{o}', { p: (o.pa * 100).toFixed(0), o: o.oa.toFixed(2) })}</small></button>
        </div>
      </div>`;
  }
  const title = `${m.home || '?'} <span class="gm-v">v</span> ${m.away || '?'}`;
  return `<div class="gm-tie"><div class="gm-tie-head"><span class="pill pill-soft">${mid}</span> ${title}</div>${body}</div>`;
}

function renderRounds() {
  $('rounds').innerHTML = ROUNDS.map((r, ri) => {
    const before = ri < ENTRY_IDX[S.entryRound];
    return `<section class="card reveal${before ? ' gm-dim' : ''}">
        <h2>${r.emoji} ${t(r.name)}${before ? ` <span class="hint">${t('(before you joined)')}</span>` : ''}</h2>
        <div class="gm-grid">${r.mids.map(tieCard).join('')}</div>
      </section>`;
  }).join('');
}

function renderAll() {
  $('entry').value = S.entryRound;
  $('entry').disabled = slotsUsed() > 0;
  $('slots').innerHTML = t('You joined from {name} → {tot} calls total, {left} left.', {
    name: `<b>${t(ROUNDS[ENTRY_IDX[S.entryRound]].name)}</b>`,
    tot: `<b>${slotsTotal()}</b>`, left: `<b>${slotsTotal() - slotsUsed()}</b>` }) +
    (slotsUsed() > 0 ? ` <span class="hint">${t('(reset to change the join round)')}</span>` : '');
  renderWallet(); renderBoard(); renderRounds();
}

function flash(msg) { $('err').textContent = msg; clearTimeout(flash.t); flash.t = setTimeout(() => ($('err').textContent = ''), 3200); }

/* ---------- actions ---------- */
function placeBet(mid, teamCode) {
  const m = A.bracket[mid];
  const pick = teamCode === 'H' ? m.home : m.away;
  const stake = Math.round(Number(document.querySelector(`.gm-stake[data-mid="${mid}"]`).value) || 0);
  if (stake < 10) return flash(t('Minimum stake is 10 Coins.'));
  if (stake > bankroll()) return flash(t('You only have {n} Coins.', { n: fmt(bankroll()) }));
  const shv = document.querySelector(`.gm-sh[data-mid="${mid}"]`).value;
  const sav = document.querySelector(`.gm-sa[data-mid="${mid}"]`).value;
  let score = null, sOdds = 0;
  if (shv !== '' && sav !== '') {
    score = [Math.max(0, Math.min(9, Math.round(+shv))), Math.max(0, Math.min(9, Math.round(+sav)))];
    sOdds = dec(scoreProb(m.home, m.away, score[0], score[1]));
  }
  const o = tieOdds(m.home, m.away);
  S.bets[mid] = { home: m.home, away: m.away, pick, score, stake, wOdds: pick === m.home ? o.oh : o.oa, sOdds };
  save(); renderAll();
}

function boot() {
  loadState();
  $('rounds').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const mid = btn.dataset.mid;
    if (btn.dataset.act === 'cancel') { delete S.bets[mid]; save(); renderAll(); }
    else if (btn.dataset.act === 'bet') placeBet(mid, btn.dataset.team);
  });
  $('entry').addEventListener('change', (e) => {
    if (slotsUsed() > 0) { e.target.value = S.entryRound; return flash(t('Reset the game first to change the join round.')); }
    S.entryRound = e.target.value; save(); renderAll();
  });
  $('reset').addEventListener('click', () => {
    if (slotsUsed() > 0 && !confirm(t('Reset the game? Your calls and Coins will be cleared.'))) return;
    S = { entryRound: S.entryRound, bets: {} }; save(); renderAll();
  });
  document.addEventListener('gf:langchange', renderAll);   // re-render dynamic text on language switch
  renderAll();
}

Promise.all([fetch('/odds.json'), fetch('/actual.json')])
  .then(async ([mr, ar]) => {
    if (!mr.ok) throw new Error(`odds.json HTTP ${mr.status}`);
    if (!ar.ok) throw new Error(`actual.json HTTP ${ar.status}`);
    M = await mr.json(); A = await ar.json();
    $('asof').textContent = `results through ${A.as_of}`;
    boot();
  })
  .catch((e) => ($('err').textContent = 'Error: ' + e.message));
