// Seed a handful of AI virtual users to test storage + the leaderboard end-to-end.
// Creates users via the Admin API, signs each in, and places random bets through the real place_bet
// RPC (so it exercises the exact server-side path: profile trigger, coin deduction, quota). Safe to
// re-run (existing users are reused). Needs the service_role key (env) + the public url/anon key
// (read from public/supabase-config.js, or SUPABASE_URL / SUPABASE_ANON_KEY env).
//
//   SUPABASE_SERVICE_KEY=... node scripts/seed_virtual_users.mjs [numUsers=6] [betsEach=3]
import { readFileSync } from 'node:fs';

function config() {
  let url = process.env.SUPABASE_URL, anon = process.env.SUPABASE_ANON_KEY;
  try {
    const c = readFileSync('public/supabase-config.js', 'utf8');
    url = url || (c.match(/url:\s*'([^']+)'/) || [])[1];
    anon = anon || (c.match(/anonKey:\s*'([^']+)'/) || [])[1];
  } catch { /* ignore */ }
  const svc = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !anon || /YOUR-/.test(url) || /YOUR-/.test(anon)) throw new Error('Set url + anonKey in public/supabase-config.js first');
  if (!svc) throw new Error('Set SUPABASE_SERVICE_KEY (service_role) in the environment');
  return { url, anon, svc };
}

// minimal odds engine (same neutral DC + ensemble blend as the site) to fill w_odds/s_odds
function makeOdds(M) {
  const K = 10, rho = M.rho || 0;
  const pois = (k, l) => { let f = 1; for (let i = 2; i <= k; i++) f *= i; return Math.exp(-l) * l ** k / f; };
  const grid = (h, a) => {
    const lh = Math.exp(M.mu + (M.attack[h] || 0) + (M.defence[a] || 0));
    const la = Math.exp(M.mu + (M.attack[a] || 0) + (M.defence[h] || 0));
    const g = []; let t = 0;
    for (let i = 0; i <= K; i++) { g[i] = []; for (let j = 0; j <= K; j++) g[i][j] = pois(i, lh) * pois(j, la); }
    g[0][0] *= 1 - lh * la * rho; g[0][1] *= 1 + lh * rho; g[1][0] *= 1 + la * rho; g[1][1] *= 1 - rho;
    for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) t += g[i][j];
    for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) g[i][j] /= t;
    return g;
  };
  const adv = (h, a) => {
    const g = grid(h, a); let ph = 0, pa = 0;
    for (let i = 0; i <= K; i++) for (let j = 0; j <= K; j++) (i > j ? (ph += g[i][j]) : i < j ? (pa += g[i][j]) : 0);
    let p = ph / (ph + pa);
    const e = M.ens, key = `${h}|${a}|0`;
    if (e && e.probs && e.probs[key]) { const pg = e.probs[key], w = e.w ?? 0.5; const dh = w * ph + (1 - w) * pg[0], da = w * pa + (1 - w) * pg[2]; p = dh / (dh + da); }
    return p;
  };
  return { adv, dec: (p) => Math.max(1.01, 1 / Math.max(p, 1e-6)) };
}

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

async function main() {
  const { url, anon, svc } = config();
  const N = parseInt(process.argv[2] || '6', 10), K = parseInt(process.argv[3] || '3', 10);
  const M = JSON.parse(readFileSync('public/odds.json', 'utf8'));
  const A = JSON.parse(readFileSync('public/actual.json', 'utf8'));
  const odds = makeOdds(M);
  const open = Object.entries(A.bracket || {})
    .filter(([, m]) => m.home && m.away && !m.played)
    .map(([mid, m]) => ({ mid, ...m }));
  if (!open.length) { console.log('No open ties to bet on right now.'); return; }

  const admin = { apikey: svc, Authorization: `Bearer ${svc}`, 'Content-Type': 'application/json' };
  let made = 0, placed = 0;
  for (let i = 1; i <= N; i++) {
    const email = `vu${i}@goalforge.test`, password = `Passw0rd!vu${i}`;
    // create (ignore "already exists")
    const cr = await fetch(`${url}/auth/v1/admin/users`, {
      method: 'POST', headers: admin,
      body: JSON.stringify({ email, password, email_confirm: true, user_metadata: { handle: `bot_${i}` } }),
    });
    if (cr.ok) made++;
    // sign in for a user JWT
    const si = await fetch(`${url}/auth/v1/token?grant_type=password`, {
      method: 'POST', headers: { apikey: anon, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const tok = (await si.json()).access_token;
    if (!tok) { console.error(`  vu${i}: sign-in failed`); continue; }
    const uh = { apikey: anon, Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json' };
    // place up to K random bets on distinct open ties
    const ties = [...open].sort(() => Math.random() - 0.5).slice(0, K);
    for (const tie of ties) {
      const home = Math.random() < odds.adv(tie.home, tie.away);
      const team = home ? tie.home : tie.away;
      const p = home ? odds.adv(tie.home, tie.away) : 1 - odds.adv(tie.home, tie.away);
      const stake = 10 * (1 + Math.floor(Math.random() * 20));   // 10..200
      const r = await fetch(`${url}/rest/v1/rpc/place_bet`, {
        method: 'POST', headers: uh,
        body: JSON.stringify({ p_match_id: tie.mid, p_pick: team, p_stake: stake, p_w_odds: +odds.dec(p).toFixed(2) }),
      });
      if (r.ok) placed++; else console.error(`  vu${i} ${tie.mid}: ${r.status} ${await r.text()}`);
    }
  }
  console.log(`seeded ${N} virtual users (${made} newly created), placed ${placed} bets across ${open.length} open ties`);
  console.log('check the leaderboard in the game, or: select * from leaderboard;');
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
