// Daily settlement for the multi-user Prediction Game (Supabase).
// Reads the real results (public/actual.json) and settles every still-pending bet: pays winners at
// the odds stored on the bet, marks losers, credits coins — all via the service-role `settle_bet`
// RPC (server-side, atomic, idempotent). Run after the results refresh (see .github/workflows).
//
//   SUPABASE_URL=... SUPABASE_SERVICE_KEY=... node scripts/settle_bets.mjs [path/to/actual.json]
//
// The settlement rule lives in the pure, dependency-free `settleBet()` below so it can be unit
// tested without a database (scripts/test_settle.mjs); it mirrors public/game.js exactly.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

// Pure rule: given a bet and its match record from actual.json (or undefined), return the outcome
// { status, payout } — or null if the tie has not been played yet (leave pending).
export function settleBet(bet, m) {
  if (!m || !m.played) return null;
  if (bet.pick !== m.winner) return { status: 'lost', payout: 0 };
  const reg = m.reg || m.actual;
  const exact = bet.score_h != null && bet.score_a != null &&
    reg && reg[0] === bet.score_h && reg[1] === bet.score_a;
  return exact
    ? { status: 'won_exact', payout: Math.round(bet.stake * Number(bet.s_odds)) }
    : { status: 'won_outcome', payout: Math.round(bet.stake * Number(bet.w_odds)) };
}

async function main() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    console.error('Set SUPABASE_URL and SUPABASE_SERVICE_KEY (service_role) in the environment.');
    process.exit(1);
  }
  const actualPath = process.argv[2] || 'public/actual.json';
  const bracket = JSON.parse(readFileSync(actualPath, 'utf8')).bracket || {};

  const h = { apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' };
  const rest = (p, init) => fetch(`${url}/rest/v1${p}`, { ...init, headers: { ...h, ...(init?.headers || {}) } });

  const pending = await (await rest(
    '/bets?status=eq.pending&select=id,user_id,match_id,pick,score_h,score_a,stake,w_odds,s_odds'
  )).json();
  if (!Array.isArray(pending)) {
    console.error('Failed to read bets:', pending);
    process.exit(1);
  }
  console.log(`${pending.length} pending bets; results as of ${actualPath}`);

  let settled = 0, won = 0, paid = 0;
  for (const bet of pending) {
    const r = settleBet(bet, bracket[bet.match_id]);
    if (!r) continue;                                        // tie not played yet
    const res = await rest('/rpc/settle_bet', {
      method: 'POST',
      body: JSON.stringify({ p_bet_id: bet.id, p_status: r.status, p_payout: r.payout }),
    });
    if (!res.ok) { console.error(`  settle ${bet.id} failed: ${res.status} ${await res.text()}`); continue; }
    settled++; if (r.payout > 0) { won++; paid += r.payout; }
  }
  console.log(`settled ${settled} bets (${won} winners, ${paid} coins paid out); ${pending.length - settled} still pending`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
