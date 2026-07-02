# Prediction Game — multi-user (Supabase) setup

The single-player game (public/game.html) needs no backend. The **multi-user** version adds sign-in
and a shared leaderboard using **Supabase** (managed Postgres + Auth), all on free tiers. Everything
in the repo is already built; this is the ~10-minute one-time setup only **you** can do (it creates
an account + secret keys). After it, tell Claude to continue and it will seed test users and verify.

## What you do (once, ~10 min)

1. **Create the project.** Go to <https://supabase.com>, sign in with GitHub (free). New project →
   pick a region near you (e.g. Singapore), set a database password, wait ~2 min for it to spin up.

2. **Create the tables.** Left sidebar → **SQL Editor** → New query → paste all of
   [`supabase/schema.sql`](../supabase/schema.sql) → **Run**. It should say success (creates the
   `profiles`/`bets` tables, security rules, and the `place_bet`/`cancel_bet` functions).

3. **Turn on a login method.** Authentication → **Providers**:
   - Easiest & free: enable **Email** (magic link) — zero external setup.
   - Optional **Google**: enable Google, then follow Supabase's link to create a Google OAuth client
     in Google Cloud Console (~5 min). Ask Claude for the exact clicks if you want this.
   - (Phone/SMS OTP needs a paid SMS provider — skip for now.)
   Under Authentication → **URL Configuration**, add your site URL (the Vercel domain, and
   `http://localhost:8641` if testing locally) to **Redirect URLs**.

4. **Grab the keys.** Project **Settings → API**, copy three things:
   - **Project URL** (like `https://abcd.supabase.co`)
   - **anon public** key (safe to expose — protected by row-level security)
   - **service_role** key (SECRET — never commit it or paste it in chat)

5. **Wire them up.**
   - Put the **Project URL** and **anon key** into [`public/supabase-config.js`](../public/supabase-config.js)
     (replace the placeholders). These are public; committing them is fine.
   - In **Vercel → your project → Settings → Environment Variables**, add (server-side, secret):
     `SUPABASE_URL` = the Project URL, `SUPABASE_SERVICE_KEY` = the **service_role** key. These power
     the daily settlement job — never put the service_role key in `public/`.
   - For GitHub Actions settlement, add the same two as **GitHub repo secrets**
     (Settings → Secrets and variables → Actions): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.

6. Tell me the **Project URL + anon key** (or just commit them into `supabase-config.js`) and confirm
   the SQL ran. Keep the service_role key to yourself (it goes only in Vercel/GitHub secrets).

## What I (Claude) do — already built, verified after your setup

- `supabase/schema.sql` — the whole database (tables, RLS, `place_bet`/`cancel_bet`, leaderboard view).
- `public/game-online.html` + `public/game-online.js` — sign-in + placing bets (via the secure
  `place_bet` RPC) + the shared live leaderboard, reusing the model's odds.
- `scripts/settle_bets.mjs` — the daily settlement job: reads the real results (public/actual.json)
  and pays out / marks pending bets, crediting coins (uses the service_role key; server-side only).
- `scripts/seed_virtual_users.mjs` — seeds a handful of AI virtual users with random predictions so we
  can test storage + the leaderboard end-to-end before real users arrive.
- `.github/workflows/settle-bets.yml` — runs the settlement job daily (after the results refresh).

## How it fits together (dataflow)

```
browser → Supabase Auth (email/Google) → session
browser → rpc place_bet(...) → Postgres validates coins/quota, inserts bet, deducts stake
daily   → settle_bets.mjs (service key) reads actual.json → pays winners, credits coins
browser → select * from leaderboard  → shared ranking (handle + coins, no emails)
```
Odds/settlement are enforced server-side (Postgres functions + the trusted settlement job); the
browser can never edit coins or other users' bets. Free tiers (Supabase ~500 MB DB / 50k MAU, Vercel
Hobby) are far more than this needs.
