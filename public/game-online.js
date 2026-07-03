/* GoalForge Prediction Game — MULTIPLAYER front end.
   Sign in with Supabase Auth, place bets through the secure place_bet RPC (server-side validation),
   and see a shared live leaderboard. No money logic here — the browser only reads and calls RPCs;
   coins/quota/settlement are enforced in Postgres. Falls back to a friendly notice until configured. */
const $ = (id) => document.getElementById(id);
const t = window.t || ((s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s));
const cfg = window.GF_SUPABASE || {};
const CONFIGURED = cfg.url && !/YOUR-PROJECT/.test(cfg.url) && cfg.anonKey && !/YOUR-ANON/.test(cfg.anonKey);

const ROUNDS = [
  { key: 'r32', name: 'Round of 32', emoji: '⚔️', mids: Array.from({ length: 16 }, (_, i) => 'M' + (73 + i)) },
  { key: 'r16', name: 'Round of 16', emoji: '🔥', mids: ['M89', 'M90', 'M91', 'M92', 'M93', 'M94', 'M95', 'M96'] },
  { key: 'qf', name: 'Quarter-finals', emoji: '💥', mids: ['M97', 'M98', 'M99', 'M100'] },
  { key: 'sf', name: 'Semi-finals', emoji: '🌟', mids: ['M101', 'M102'] },
  { key: 'final', name: 'Final', emoji: '🏆', mids: ['M104'] },
];
const QUOTA = { r32: 4, r16: 3, qf: 2, sf: 1 };
const ENTRY_IDX = { r32: 0, r16: 1, qf: 2, sf: 3 };
const midIdx = {};
ROUNDS.forEach((r, ri) => r.mids.forEach((m) => (midIdx[m] = ri)));

let M, A, sb, session = null, profile = null, myBets = [], board = [];
let authMode = 'signup';                                        // 'signup' (first time) | 'login' (returning)

/* ---- odds engine: identical neutral Dixon-Coles + ensemble blend as game.js ---- */
function pois(k, l) { let f = 1; for (let i = 2; i <= k; i++) f *= i; return Math.exp(-l) * Math.pow(l, k) / f; }
function grid(h, a) {
  const K = 10, rho = M.rho || 0;
  const lh = Math.exp(M.mu + (M.attack[h] || 0) + (M.defence[a] || 0));
  const la = Math.exp(M.mu + (M.attack[a] || 0) + (M.defence[h] || 0));
  const g = [];
  for (let i = 0; i <= K; i++) { g[i] = []; for (let j = 0; j <= K; j++) g[i][j] = pois(i, lh) * pois(j, la); }
  g[0][0] *= 1 - lh * la * rho; g[0][1] *= 1 + lh * rho; g[1][0] *= 1 + la * rho; g[1][1] *= 1 - rho;
  let tot = 0; for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) tot += g[i][j];
  for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) g[i][j] /= tot;
  return { g, K };
}
function outcome(h, a) {
  const { g, K } = grid(h, a); let ph = 0, pd = 0, pa = 0;
  for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) { if (i > j) ph += g[i][j]; else if (i === j) pd += g[i][j]; else pa += g[i][j]; }
  const e = M.ens, key = h + '|' + a + '|0';
  if (e && e.probs && e.probs[key]) {
    const pg = e.probs[key], w = (e.w == null ? 0.5 : e.w);
    const p = [w * ph + (1 - w) * pg[0], w * pd + (1 - w) * pg[1], w * pa + (1 - w) * pg[2]];
    const s = p[0] + p[1] + p[2]; return { ph: p[0] / s, pd: p[1] / s, pa: p[2] / s };
  }
  return { ph, pd, pa };
}
const advProb = (h, a) => { const { ph, pa } = outcome(h, a); return ph / (ph + pa); };
const scoreProb = (h, a, i, j) => { const { g, K } = grid(h, a); return (i >= 0 && j >= 0 && i <= K && j <= K) ? Math.max(g[i][j], 1e-6) : 1e-6; };
const dec = (p) => Math.max(1.01, 1 / Math.max(p, 1e-6));
const tieOdds = (h, a) => { const p = advProb(h, a); return { ph: p, pa: 1 - p, oh: dec(p), oa: dec(1 - p) }; };
const fmt = (x) => Math.round(x).toLocaleString();
const flash = (m) => { $('err').textContent = m; clearTimeout(flash.t); flash.t = setTimeout(() => ($('err').textContent = ''), 4000); };

/* ---- data + auth ---- */
async function reloadUser() {
  if (!session) { profile = null; myBets = []; return; }
  const uid = session.user.id;
  const [{ data: p }, { data: b }] = await Promise.all([
    sb.from('profiles').select('*').eq('id', uid).maybeSingle(),
    sb.from('bets').select('*').eq('user_id', uid).order('created_at', { ascending: true }),
  ]);
  profile = p; myBets = b || [];
}
async function reloadBoard() {
  const { data } = await sb.from('leaderboard').select('*').limit(50);
  board = data || [];
}

async function refresh() { await Promise.all([reloadUser(), reloadBoard()]); render(); }

/* ---- rendering ---- */
function render() {
  if (!CONFIGURED) return renderNotConfigured();
  if (!session) return renderSignedOut();
  renderGame();
}

function renderNotConfigured() {
  $('app').innerHTML = `<section class="card reveal"><h2>${t('🔌 Not configured yet')}</h2>
    <div class="mnote"><p>The multiplayer game needs a (free) Supabase project. Fill in
    <code>public/supabase-config.js</code> and follow
    <a href="https://github.com/aevum-orrin/GoalForge-AI/blob/main/docs/game-online-setup.md">docs/game-online-setup.md</a>.
    Meanwhile, the <a href="game.html">solo game</a> works with no sign-in.</p></div></section>`;
}

function renderSignedOut() {
  const signup = authMode === 'signup';
  const googleBtn = cfg.enableGoogle
    ? `<button class="gm-auth-btn gm-auth-google" id="google">
         <span class="gm-g">G</span>${signup ? t('Sign up with Google') : t('Log in with Google')}</button>`
    : '';
  $('app').innerHTML = `<section class="card reveal gm-auth">
      <div class="gm-auth-tabs" role="tablist">
        <button class="gm-tab ${signup ? 'gm-tab-on' : ''}" data-mode="signup">${t('Sign up')}</button>
        <button class="gm-tab ${signup ? '' : 'gm-tab-on'}" data-mode="login">${t('Log in')}</button>
      </div>
      <h2 class="gm-auth-h">${signup ? t('Create your account') : t('Welcome back')}</h2>
      <p class="gm-auth-sub">${t('Free, no real money. We only store a display name and your Coins.')}</p>
      <label class="gm-auth-lbl" for="email">${t('Email address')}</label>
      <input type="email" id="email" class="gm-auth-input" placeholder="you@example.com" autocomplete="email" inputmode="email">
      <button class="gm-auth-btn gm-auth-primary" id="magic">
        ${signup ? t('Email me a sign-up link') : t('Email me a login link')}</button>
      ${googleBtn}
      <p class="gm-auth-alt">${signup ? t('Already have an account?') : t('New here?')}
        <a href="#" id="swap">${signup ? t('Log in') : t('Sign up')}</a></p>
    </section>`;
  $('app').querySelectorAll('.gm-tab').forEach((b) => (b.onclick = () => { authMode = b.dataset.mode; renderSignedOut(); }));
  $('swap').onclick = (e) => { e.preventDefault(); authMode = signup ? 'login' : 'signup'; renderSignedOut(); };
  $('magic').onclick = async () => {
    const email = $('email').value.trim();
    if (!email) return flash(t('Enter your email first.'));
    const { error } = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.href, shouldCreateUser: signup } });
    flash(error ? error.message : (signup ? t('Check your inbox to confirm and start playing.') : t('Check your inbox for the sign-in link.')));
  };
  if (cfg.enableGoogle) $('google').onclick = async () => {
    const { error } = await sb.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.href } });
    if (error) flash(error.message);
  };
}

function renderGame() {
  if (!profile) { $('app').innerHTML = `<section class="card reveal"><p class="hint">${t('Setting up your profile…')}</p></section>`; return; }
  const quota = QUOTA[profile.join_round] || 4;
  const used = myBets.filter((b) => b.status !== 'cancelled').length;
  const betByMid = Object.fromEntries(myBets.map((b) => [b.match_id, b]));

  const wallet = `<section class="statstrip gm-wallet">
      <div class="tile tile-violet"><div class="tile-emoji">🧑</div><div class="tile-big" style="font-size:22px">${profile.handle}</div>
        <div class="tile-label">${t('Signed in')}</div><div class="tile-sub"><a href="#" id="signout">${t('sign out')}</a></div></div>
      <div class="tile tile-green"><div class="tile-emoji">💰</div><div class="tile-big">${fmt(profile.coins)}</div>
        <div class="tile-label">Coins</div><div class="tile-sub">${t('start 1,000')}</div></div>
      <div class="tile tile-sky"><div class="tile-emoji">🎟️</div><div class="tile-big">${used}/${quota}</div>
        <div class="tile-label">${t('Calls used')}</div><div class="tile-sub">${t('{n} left', { n: quota - used })}</div></div>
      <div class="tile tile-amber"><div class="tile-emoji">🏆</div><div class="tile-big" style="font-size:22px">${boardRank()}</div>
        <div class="tile-label">${t('Your rank')}</div><div class="tile-sub">${t('of {n}', { n: mergedBoard().length })}</div></div>
    </section>`;

  const rounds = ROUNDS.map((r) => {
    const cards = r.mids.map((mid) => tieCard(mid, betByMid[mid], used, quota, profile)).filter(Boolean).join('');
    return cards ? `<section class="card reveal"><h2>${r.emoji} ${t(r.name)}</h2><div class="gm-grid">${cards}</div></section>` : '';
  }).join('');

  // First-timer onboarding: only while they still have every call and there are ties to place them on.
  const welcome = (used === 0 && rounds)
    ? `<section class="card reveal gm-guide"><h2>${t('👋 Welcome, {handle}', { handle: profile.handle })}</h2>
        <div class="mnote"><p>${t('You have {n} calls this tournament. Back a team to go through in any open tie below — longer odds pay more, and calling the exact score lands a much bigger bonus. Picks settle automatically as results come in.', { n: quota })}</p></div></section>`
    : '';

  $('app').innerHTML = wallet
    + welcome
    + `<section class="card reveal"><h2>${t('🏆 Leaderboard')}</h2><div class="gm-board">${leaderboardHtml()}</div></section>`
    + (rounds || `<section class="card reveal"><p class="hint">${t('No open ties to call right now — check back as the bracket fills in.')}</p></section>`);

  $('signout').onclick = async (e) => { e.preventDefault(); await sb.auth.signOut(); };
  bindActions();
}

const INIT = 1000;                                              // starting coins — same as every player
function baseline() {                                           // 🤖 model: backs its pick, flat 100, on every PLAYED tie
  let b = INIT, settled = 0;
  for (const r of ROUNDS) for (const mid of r.mids) {
    const m = (A.bracket || {})[mid];
    if (!m || !m.home || !m.away || !m.played) continue;
    const p = advProb(m.home, m.away), pick = p >= 0.5 ? m.home : m.away, stake = 100;
    b -= stake; if (m.winner === pick) b += stake * dec(Math.max(p, 1 - p)); settled++;
  }
  return { coins: Math.round(b), settled };
}
function mergedBoard() {                                        // DB players + the deterministic model benchmark, ranked
  const bot = baseline();
  const model = { id: '__model__', handle: '🤖 ' + t('Model'), coins: bot.coins, bets_settled: bot.settled, bets_placed: bot.settled, __model: true };
  return [...board, model].sort((a, c) => c.coins - a.coins);
}

function boardRank() {
  if (!profile) return '—';
  const i = mergedBoard().findIndex((r) => r.id === profile.id);
  return i >= 0 ? '#' + (i + 1) : '—';
}

function leaderboardHtml() {
  return mergedBoard().map((r, i) => `<div class="gm-rank ${r.__model ? 'gm-model' : ''} ${profile && r.id === profile.id ? 'gm-lead' : ''}">
      <span class="gm-medal">${i === 0 ? '👑' : '#' + (i + 1)}</span>
      <span class="gm-who">${r.handle}</span>
      <span class="gm-rsub">${r.__model ? t('backs its pick every tie · {n} settled', { n: r.bets_settled }) : t('{n}/{m} settled', { n: r.bets_settled, m: r.bets_placed })}</span>
      <span class="gm-coins">${fmt(r.coins)} <small>Coins</small></span></div>`).join('');
}

function tieCard(mid, bet, used, quota, prof) {
  const m = (A.bracket || {})[mid] || {};
  const known = m.home && m.away;
  const bettableRound = midIdx[mid] >= (ENTRY_IDX[prof.join_round] ?? 0);
  if (bet) {
    const badge = { pending: t('⏳ Pending'), won_outcome: t('✅ Won · outcome'), won_exact: t('🎯 Won · exact!'), lost: t('❌ Lost'), cancelled: t('✖ Cancelled') }[bet.status] || bet.status;
    const cls = { pending: 'gm-pending', won_outcome: 'gm-won', won_exact: 'gm-won gm-exact', lost: 'gm-lost', cancelled: 'gm-lost' }[bet.status] || '';
    const fine = bet.s_odds > 0
      ? t('Stake {n} · outcome ×{o} · score ×{s}', { n: fmt(bet.stake), o: Number(bet.w_odds).toFixed(2), s: Number(bet.s_odds).toFixed(1) })
      : t('Stake {n} · outcome ×{o}', { n: fmt(bet.stake), o: Number(bet.w_odds).toFixed(2) });
    return `<div class="gm-tie"><div class="gm-tie-head"><span class="pill pill-soft">${mid}</span> ${m.home} <span class="gm-v">v</span> ${m.away}</div>
      <div class="gm-slip ${cls}">
        <div><b>${t('Backed:')}</b> ${bet.pick}${bet.score_h != null ? ' · ' + t('exact {h}–{a}', { h: bet.score_h, a: bet.score_a }) : ''}</div>
        <div class="gm-fine">${fine}</div>
        <div class="gm-badge">${badge}${bet.payout ? ` · +${fmt(bet.payout)}` : (bet.status === 'lost' ? ` · −${fmt(bet.stake)}` : '')}</div>
        ${bet.status === 'pending' ? `<button class="gm-mini" data-cancel="${bet.id}">${t('Cancel (refund)')}</button>` : ''}
      </div></div>`;
  }
  if (!known || m.played || !bettableRound || used >= quota) return '';   // only open, in-quota ties get a form
  const o = tieOdds(m.home, m.away);
  return `<div class="gm-tie"><div class="gm-tie-head"><span class="pill pill-soft">${mid}</span> ${m.home} <span class="gm-v">v</span> ${m.away}</div>
      <div class="gm-form">
        <div class="gm-stakerow">
          <label class="gm-lbl">${t('Stake')} <input type="number" class="gm-stake" data-mid="${mid}" value="100" min="10" step="10"></label>
          <label class="gm-lbl">${t("Exact 120' score")} <span class="gm-opt">${t('(optional)')}</span>
            <span class="gm-scorein"><input type="number" class="gm-sh" data-mid="${mid}" min="0" max="9" placeholder="${m.home.slice(0, 3)}">
            <span class="gm-dash">–</span><input type="number" class="gm-sa" data-mid="${mid}" min="0" max="9" placeholder="${m.away.slice(0, 3)}"></span></label>
        </div>
        <div class="gm-picks">
          <button class="gm-pick" data-bet="${mid}" data-team="H">${t('Back {team}', { team: m.home })}<small>${t('advance {p}% · pays ×{o}', { p: (o.ph * 100).toFixed(0), o: o.oh.toFixed(2) })}</small></button>
          <button class="gm-pick" data-bet="${mid}" data-team="A">${t('Back {team}', { team: m.away })}<small>${t('advance {p}% · pays ×{o}', { p: (o.pa * 100).toFixed(0), o: o.oa.toFixed(2) })}</small></button>
        </div>
      </div></div>`;
}

function bindActions() {
  $('app').querySelectorAll('button[data-bet]').forEach((btn) => (btn.onclick = () => placeBet(btn.dataset.bet, btn.dataset.team)));
  $('app').querySelectorAll('button[data-cancel]').forEach((btn) => (btn.onclick = () => cancelBet(btn.dataset.cancel)));
}

async function placeBet(mid, team) {
  const m = A.bracket[mid];
  const pick = team === 'H' ? m.home : m.away;
  const stake = Math.round(Number($('app').querySelector(`.gm-stake[data-mid="${mid}"]`).value) || 0);
  if (stake < 10) return flash(t('Minimum stake is 10 Coins.'));
  const shv = $('app').querySelector(`.gm-sh[data-mid="${mid}"]`).value;
  const sav = $('app').querySelector(`.gm-sa[data-mid="${mid}"]`).value;
  const o = tieOdds(m.home, m.away);
  let sh = null, sa = null, sOdds = 0;
  if (shv !== '' && sav !== '') {
    sh = Math.max(0, Math.min(9, Math.round(+shv))); sa = Math.max(0, Math.min(9, Math.round(+sav)));
    sOdds = dec(scoreProb(m.home, m.away, sh, sa));
  }
  const { error } = await sb.rpc('place_bet', {
    p_match_id: mid, p_pick: pick, p_stake: stake,
    p_w_odds: Number((pick === m.home ? o.oh : o.oa).toFixed(2)),
    p_score_h: sh, p_score_a: sa, p_s_odds: Number(sOdds.toFixed(2)),
  });
  if (error) return flash(error.message);
  await refresh();
}

async function cancelBet(id) {
  const { error } = await sb.rpc('cancel_bet', { p_bet_id: id });
  if (error) return flash(error.message);
  await refresh();
}

async function boot() {
  if (!CONFIGURED) return render();
  sb = window.supabase.createClient(cfg.url, cfg.anonKey);
  try {
    [M, A] = await Promise.all([fetch('/odds.json').then((r) => r.json()), fetch('/actual.json').then((r) => r.json())]);
  } catch (e) { return ($('err').textContent = 'Failed to load fixtures: ' + e.message); }
  sb.auth.onAuthStateChange((_e, s) => { session = s; refresh(); });
  const { data } = await sb.auth.getSession();
  session = data.session;
  await refresh();
}

document.addEventListener('gf:langchange', () => render());   // re-render the dynamic UI on EN/中文 toggle
boot();
