-- GoalForge Prediction Game — multi-user backend schema (Supabase / Postgres).
-- Run this once in your Supabase project: SQL Editor -> paste -> Run.
--
-- Design for integrity on a free, backend-light stack: the browser only AUTHENTICATES and CALLS
-- SECURITY DEFINER functions; it can never write coins or bets directly. All money logic lives in
-- Postgres (place_bet / cancel_bet) or in the trusted daily settlement job (service_role key).
--   * profiles: one row per signed-in user (starting coins, chosen join round).
--   * bets:     one row per prediction; status/payout are set only by settlement.
-- Row-Level Security is on everywhere; direct INSERT/UPDATE/DELETE on money columns is denied.

-- ---------- tables ----------------------------------------------------------------------------
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  handle      text not null,
  coins       integer not null default 1000 check (coins >= 0),
  join_round  text    not null default 'r32' check (join_round in ('r32','r16','qf','sf')),
  created_at  timestamptz not null default now()
);

create table if not exists public.bets (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.profiles (id) on delete cascade,
  match_id    text not null,                              -- 'M73'..'M104'
  pick        text not null,                              -- team predicted to advance
  score_h     integer check (score_h between 0 and 20),   -- optional exact 120' score (null = outcome only)
  score_a     integer check (score_a between 0 and 20),
  stake       integer not null check (stake >= 10),
  w_odds      numeric(6,2) not null check (w_odds >= 1),  -- outcome odds at bet time
  s_odds      numeric(8,2) not null default 0,            -- exact-score odds at bet time (0 if no score)
  status      text not null default 'pending'
              check (status in ('pending','won_outcome','won_exact','lost','cancelled')),
  payout      integer not null default 0 check (payout >= 0),
  created_at  timestamptz not null default now(),
  settled_at  timestamptz,
  unique (user_id, match_id)                              -- one bet per tie per user
);

create index if not exists bets_user_idx on public.bets (user_id);
create index if not exists bets_match_idx on public.bets (match_id);
create index if not exists bets_status_idx on public.bets (status);

-- ---------- row-level security ----------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.bets     enable row level security;

-- profiles hold no PII (email lives in auth.users) -> readable by all for the leaderboard,
-- but NOT directly writable (no insert/update/delete policy => denied; only definer fns touch coins).
drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles for select using (true);

-- users may read only their own bets; no direct writes (place_bet / cancel_bet do it).
drop policy if exists bets_read_own on public.bets;
create policy bets_read_own on public.bets for select using (auth.uid() = user_id);

-- ---------- new-user provisioning -------------------------------------------------------------
-- auto-create a profile (1000 coins) the moment someone signs up.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, handle)
  values (new.id, coalesce(nullif(split_part(new.email, '@', 1), ''), 'player'))
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- helpers: round of a match, and per-join-round quota --------------------------------
create or replace function public.match_round_idx(m text)
returns integer language sql immutable as $$
  select case
    when m in ('M73','M74','M75','M76','M77','M78','M79','M80',
               'M81','M82','M83','M84','M85','M86','M87','M88') then 0   -- Round of 32
    when m in ('M89','M90','M91','M92','M93','M94','M95','M96') then 1   -- Round of 16
    when m in ('M97','M98','M99','M100') then 2                         -- Quarter-finals
    when m in ('M101','M102') then 3                                    -- Semi-finals
    when m = 'M104' then 4                                              -- Final
    else -1 end;
$$;

create or replace function public.round_quota(r text)
returns integer language sql immutable as $$
  select case r when 'r32' then 4 when 'r16' then 3 when 'qf' then 2 when 'sf' then 1 else 0 end;
$$;

create or replace function public.round_idx(r text)
returns integer language sql immutable as $$
  select case r when 'r32' then 0 when 'r16' then 1 when 'qf' then 2 when 'sf' then 3 else 99 end;
$$;

-- ---------- place a bet (atomic: validate + insert + deduct) -----------------------------------
create or replace function public.place_bet(
  p_match_id text, p_pick text, p_stake integer,
  p_w_odds numeric, p_score_h integer default null, p_score_a integer default null,
  p_s_odds numeric default 0)
returns public.bets language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  prof public.profiles;
  used integer;
  b public.bets;
begin
  if uid is null then raise exception 'not signed in'; end if;
  select * into prof from public.profiles where id = uid for update;
  if not found then raise exception 'no profile'; end if;

  if match_round_idx(p_match_id) < round_idx(prof.join_round) then
    raise exception 'this tie is before your join round';
  end if;

  select count(*) into used from public.bets
    where user_id = uid and status <> 'cancelled';
  if used >= round_quota(prof.join_round) then
    raise exception 'no predictions left (quota %)' , round_quota(prof.join_round);
  end if;

  if p_stake < 10 then raise exception 'minimum stake is 10'; end if;
  if p_stake > prof.coins then raise exception 'not enough coins'; end if;

  update public.profiles set coins = coins - p_stake where id = uid;
  insert into public.bets (user_id, match_id, pick, score_h, score_a, stake, w_odds, s_odds)
    values (uid, p_match_id, p_pick, p_score_h, p_score_a, p_stake, p_w_odds,
            case when p_score_h is not null and p_score_a is not null then coalesce(p_s_odds,0) else 0 end)
    returning * into b;
  return b;
exception when unique_violation then
  raise exception 'you already have a bet on this tie';
end; $$;

-- ---------- cancel a still-pending bet (refund the stake) --------------------------------------
create or replace function public.cancel_bet(p_bet_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare uid uuid := auth.uid(); b public.bets;
begin
  if uid is null then raise exception 'not signed in'; end if;
  select * into b from public.bets where id = p_bet_id and user_id = uid for update;
  if not found then raise exception 'bet not found'; end if;
  if b.status <> 'pending' then raise exception 'already settled'; end if;
  update public.profiles set coins = coins + b.stake where id = uid;
  update public.bets set status = 'cancelled' where id = b.id;
end; $$;

-- ---------- settlement (service_role only: set a bet's result and credit coins atomically) ------
-- Called by scripts/settle_bets.mjs with the service_role key. NOT granted to authenticated, so
-- users can never settle their own bets. On a win, payout (which already includes the stake) is
-- credited back to coins; the stake was deducted at place_bet time.
create or replace function public.settle_bet(p_bet_id uuid, p_status text, p_payout integer)
returns void language plpgsql security definer set search_path = public as $$
declare b public.bets;
begin
  if p_status not in ('won_outcome','won_exact','lost') then
    raise exception 'bad status %', p_status;
  end if;
  select * into b from public.bets where id = p_bet_id for update;
  if not found then raise exception 'bet not found'; end if;
  if b.status <> 'pending' then return; end if;             -- idempotent: already settled
  update public.bets set status = p_status, payout = greatest(p_payout, 0), settled_at = now()
    where id = b.id;
  if p_payout > 0 then
    update public.profiles set coins = coins + p_payout where id = b.user_id;
  end if;
end; $$;

revoke execute on function public.settle_bet(uuid, text, integer) from anon, authenticated;

-- ---------- public leaderboard (handle + coins only; no emails) --------------------------------
create or replace view public.leaderboard as
  select p.id, p.handle, p.coins,
         (select count(*) from public.bets b where b.user_id = p.id and b.status <> 'cancelled') as bets_placed,
         (select count(*) from public.bets b where b.user_id = p.id and b.status in ('won_outcome','won_exact','lost')) as bets_settled
  from public.profiles p
  order by p.coins desc, p.created_at asc;

grant select on public.leaderboard to anon, authenticated;
grant execute on function public.place_bet(text,text,integer,numeric,integer,integer,numeric) to authenticated;
grant execute on function public.cancel_bet(uuid) to authenticated;
