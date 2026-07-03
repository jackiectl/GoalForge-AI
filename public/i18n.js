/* Lightweight, dependency-free bilingual (EN/ZH) layer for the static site chrome.
   Strategy: translate by source string. Leaf chrome elements (nav, titles, section headers,
   home-card text) are matched on their English text and swapped; the few subtitles that contain
   markup carry an explicit data-i18n key. A 🌐 toggle is injected into the nav and the choice is
   remembered in localStorage. Anything not in the dictionary (dynamic JS-rendered tables, cards,
   the game UI, footers) simply stays English — a safe fallback, translated in a later pass. */
(function () {
  const LANG_KEY = 'gf_lang';
  const norm = (s) => s.replace(/\s+/g, ' ').trim();
  const getLang = () => (localStorage.getItem(LANG_KEY) === 'zh' ? 'zh' : 'en');

  // ---- dictionary ----------------------------------------------------------------------------
  const DICT = {                                 // English (normalised) -> 中文; used by both
                                                 // content-matching (static chrome) and t() (dynamic)
    // nav + card titles (shared)
    'Match Predictor': '对阵预测',
    'Full Tournament': '全程赛事',
    'Honors': '个人荣誉',
    'Prediction vs Actual': '预测 vs 实际',
    'Live Re-forecast': '动态重预测',
    'Prediction Game': '竞猜游戏',
    // page titles (h1)
    '⚔️ Match Predictor': '⚔️ 对阵预测',
    '🗓️ Full Tournament Prediction': '🗓️ 全程赛事预测',
    '🏅 Honors & Leaderboards': '🏅 个人荣誉与榜单',
    '🎯 Prediction vs Actual': '🎯 预测 vs 实际',
    '🔄 Live Re-forecast': '🔄 动态重预测',
    '🎮 Prediction Game': '🎮 竞猜游戏',
    // section headers (h2)
    '🎯 How it works': '🎯 玩法说明',
    "ℹ️ What's different between the two": 'ℹ️ 两者有何不同',
    '🏆 Knockout bracket — predicted path': '🏆 淘汰赛对阵图 — 预测路径',
    '🔥 Knockout bracket — real results as they land': '🔥 淘汰赛对阵图 — 实时真实结果',
    '🏆 Leaderboard': '🏆 排行榜',
    '🔄 Live bracket — real results so far + re-projected rest': '🔄 动态对阵图 — 已赛真实结果 + 其余重预测',
    '📊 Original pre-tournament champion odds': '📊 赛前原始夺冠概率',
    '🏆 Predicted champion tracker': '🏆 预测冠军追踪',
    '⚙️ Your game': '⚙️ 你的游戏',
    'Individual awards accumulated over the predicted tournament — two complementary views':
      '在预测的整届赛事中累积的个人奖项 —— 两个互补的视角',
    // home-card call-to-action
    'Predict a match →': '预测一场对阵 →',
    'See the whole bracket →': '查看完整赛程 →',
    'View the boards →': '查看榜单 →',
    'Check the scorecard →': '查看对照 →',
    'See the live bracket →': '查看动态对阵图 →',
    'Play the game →': '开始游戏 →',
    // home-card descriptions
    "Pick any two of the 48 qualified teams and a starting XI. Get the most likely score, win/draw/loss odds, and each player's probability to score or assist.":
      '从 48 支参赛队中任选两队及首发 11 人,得到最可能比分、胜/平/负概率,以及每名球员的进球或助攻概率。',
    'Every match predicted, group stage to final: all 72 group games with standings, the real FIFA bracket rules (Annex C third-place slotting), and the knockout road to the title.':
      '从小组赛到决赛逐场预测:72 场小组赛及积分榜、真实 FIFA 赛制(附录 C 第三名分配),以及通往冠军的淘汰赛之路。',
    'Accumulated over the predicted tournament: the Golden Boot and Playmaker leaderboards, Golden Glove, plus Monte-Carlo title odds from 20,000 simulated tournaments.':
      '在预测的整届赛事中累积:金靴与助攻王榜单、金手套,以及 2 万次蒙特卡洛模拟得出的夺冠概率。',
    'The forecast was frozen at kick-off (2026-06-11), so every real match is an out-of-sample test. See our group-stage scorecard against the actual 2026 results as they come in.':
      '预测在开赛日(2026-06-11)冻结,因此每场真实比赛都是样本外检验。看看我们的小组赛成绩单如何对照 2026 年的真实结果。',
    'The dynamic twin of the frozen forecast: refit on every game played so far and re-project the real bracket to a live champion. Watch the two predictions diverge.':
      '冻结预测的动态孪生:用已踢的每场比赛重新拟合,把真实赛程重新推演到一个动态冠军。看两份预测如何分道扬镳。',
    "A just-for-fun game with virtual Coins — no real money. Call the knockout ties at the model's own odds, chase exact scores for bigger rewards, and race the model on the leaderboard.":
      '用虚拟 Coins 的趣味游戏 —— 不涉及真钱。按模型赔率竞猜淘汰赛对阵,猜中精确比分赢更多,并在排行榜上与模型一较高下。',
    // --- Prediction Game, dynamic (rendered by game.js; {..} are interpolated values) ---
    'started with {n}': '初始 {n}',
    'Calls used': '已用次数',
    '{n} left': '剩 {n}',
    'Settled': '已结算',
    '{n} pending': '{n} 待结算',
    'Net P/L': '净盈亏',
    'vs start': '相对初始',
    'You': '你',
    'Model': '模型',
    '{n}/{m} calls placed': '已下 {n}/{m} 注',
    'backs its pick every tie · {n} settled': '每场押模型的选择 · 已结算 {n}',
    'Backed:': '已押:',
    '{team} to advance': '{team} 晋级',
    'exact {h}–{a}': '精确 {h}–{a}',
    'Stake {n} · outcome ×{o}': '投注 {n} · 常规赔率 ×{o}',
    'Stake {n} · outcome ×{o} · score ×{s}': '投注 {n} · 常规 ×{o} · 比分 ×{s}',
    '⏳ Pending': '⏳ 待定',
    '✅ Won · outcome': '✅ 命中 · 胜负',
    '🎯 Won · exact score!': '🎯 命中 · 精确比分!',
    '❌ Lost': '❌ 未中',
    'Real: {line}': '实际:{line}',
    'Cancel (refund)': '撤单(退还)',
    'Waiting on the teams for this tie': '该对阵的队伍待定',
    'Already played — {line}': '已开赛 —— {line}',
    'Model backed {team}': '模型押 {team}',
    '✓ hit': '✓ 命中',
    '✗ miss': '✗ 未中',
    'Before you joined · reference odds {a}% / {b}%': '加入前 · 参考赔率 {a}% / {b}%',
    'All {n} calls used — reset to play again': '{n} 次已用完 —— 重置后再玩',
    'Stake': '投注',
    "Exact 120' score": "120' 精确比分",
    '(optional — pays more)': '(可选 —— 赔更高)',
    'Back {team}': '押 {team}',
    'advance {p}% · pays ×{o}': '晋级 {p}% · 赔 ×{o}',
    'Round of 32': '32 强',
    'Round of 16': '16 强',
    'Quarter-finals': '8 强',
    'Semi-finals': '半决赛',
    'Final': '决赛',
    '(before you joined)': '(加入前)',
    'You joined from {name} → {tot} calls total, {left} left.': '你从 {name} 加入 → 共 {tot} 次,剩 {left} 次。',
    '(reset to change the join round)': '(重置后可改加入轮次)',
    'Minimum stake is 10 Coins.': '最低投注 10 Coins。',
    'You only have {n} Coins.': '你只有 {n} Coins。',
    'Reset the game first to change the join round.': '请先重置游戏,再更改加入轮次。',
    'Reset the game? Your calls and Coins will be cleared.': '重置游戏?你的下注与 Coins 将被清空。',
    'pens {a}–{b}': '点球 {a}–{b}',
    // ===== Phase 2: dynamic strings rendered by the page scripts (shared keys deduped) =====
    // shared table / label vocabulary
    'Team': '球队', 'Pos': '位置', 'Player': '球员', 'Pts': '积分', 'xPts': '期望积分',
    'GD': '净胜球', 'GF:GA': '进球:失球', 'W-D-L': '胜-平-负', 'win': '胜', 'draw': '平',
    'Group': '小组', 'All': '全部', 'All groups': '全部小组', 'details': '详情',
    'Predicted': '预测', 'Actual': '实际', 'predicted vs actual': '预测 vs 实际',
    'advanced': '晋级', 'adv': '晋级', 'upcoming': '待赛', 'exact': '精确', 'outcome': '胜负', 'miss': '未中',
    'Predicted champion': '预测冠军', 'Error:': '错误:', 'Error: {msg}': '错误:{msg}',
    // honors.js
    '{n} goals on the modal path': '最可能路径上 {n} 个进球',
    'Golden Glove pick:': '金手套之选:',
    'deepest-run defence, {conceded} goals conceded in {matches} predicted matches ({perMatch}/match).': '走得最远的后防,{matches} 场预测比赛失球 {conceded} 个(场均 {perMatch})。',
    '{n}k sims': '{n}k 次模拟', '{n} goals': '{n} 个进球',
    // tournament.js
    'Group {x}': '小组 {x}',
    'pts {p} · gd {gd} · gf {gf}': '积分 {p} · 净胜球 {gd} · 进球 {gf}',
    'Group stage — all 12 groups': '小组赛 —— 全部 12 个小组',
    'Most likely score per match; standings use the official 2026 tiebreakers (head-to-head first).': '每场比赛取最可能比分;积分榜采用官方 2026 排名规则(优先比较相互战绩)。',
    '= expected points over all outcomes.': '= 综合所有可能结果的期望积分。',
    'top two advance': '前两名晋级', 'third (may advance)': '第三名(可能晋级)',
    'Click a group for all six matches.': '点击任一小组查看全部六场比赛。',
    'Third-place ranking — 8 of 12 advance': '各组第三名排名 —— 12 队中 8 队晋级',
    'predicted to advance to the round of 32.': '预测晋级 32 强。',
    'All six matches — predicted': '全部六场比赛 —— 预测',
    // compare.js
    'results through {d}': '结果截至 {d}',
    'Outcome accuracy': '胜负命中率', '{n}/{m} W/D/L correct': '{n}/{m} 胜平负正确',
    'Exact scoreline': '精确比分', '{n}/{m} spot-on': '{n}/{m} 完全命中',
    'RPS on real games': '真实比赛 RPS', 'beats base-rate {r}': '优于基准 {r}', 'vs base-rate {r}': '对比基准 {r}',
    'Qualifiers called': '出线球队命中', 'plus {n}/{m} group top-2': '另加 {n}/{m} 小组前二',
    'Alive': '仍存活', 'Out': '已出局', 'still in the tournament': '仍在参赛', 'already eliminated': '已被淘汰',
    'Our pre-tournament pick <b>{champ}</b> is {status}. Across the 12 groups we correctly placed <b>{top2}</b> of the top-two spots and <b>{r32}</b> of the eventual round-of-32 teams.': '我们赛前选择的 <b>{champ}</b> {status}。在全部 12 个小组中,我们正确预测了前二席位中的 <b>{top2}</b> 个,以及最终 32 强球队中的 <b>{r32}</b> 支。',
    'Group {g}': '{g} 组', 'Team (actual)': '球队(实际)',
    'Group stage — final tables': '小组赛最终排名',
    'The real 2026 group tables. {badge} reached the round of 32. Click a group to see our prediction beside reality, match by match.': '2026 年真实小组排名。{badge} 表示已晋级 32 强。点击某个小组,逐场查看预测与实际的对比。',
    'All six matches — our score → real score': '全部六场比赛 — 我们的比分 → 真实比分',
    'Champion (TBD)': '冠军(待定)',
    // app.js
    'Neutral venue — World Cup default (no home advantage).': '中立场地 — 世界杯默认(无主场优势)。',
    'Home advantage: {host} (2026 host)': '主场优势:{host}(2026 东道主)',
    'Home advantage: {host}': '主场优势:{host}',
    '{n} caps': '出场 {n}', '{n} gls': '进球 {n}', 'Bench': '替补',
    'Simulating…': '模拟中…', 'Predict': '预测', 'Draw': '平局',
    '<b>{score}</b> projected · expected goals {eg} · most likely exact: {likely}': '预计 <b>{score}</b> · 期望进球 {eg} · 最可能精确比分:{likely}',
    '{team} — scorers': '{team} — 射手', '{team} — assisters': '{team} — 助攻',
    'Scoreline': '比分', 'Scorers': '射手', 'Assists': '助攻', 'Default XI': '默认首发', 'Venue': '场地',
    'Team layer held-out backtest on international matches: RPS {rps} (lower is better — beats Elo &amp; base-rate). The scorer &amp; assist layers are history/prior-based and are <b>not</b> validated on 2026 outcomes.': '球队层在国际比赛上的留出回测:RPS {rps}(越低越好 — 优于 Elo 与基础比率)。射手与助攻层基于历史/先验,<b>未</b>在 2026 赛果上验证。',
    '· {n}k sims · ~{g} goals': '· {n}k 次模拟 · ~{g} 进球',
    'Init error: {msg}': '初始化错误:{msg}',
    // bracket.js
    'TBD': '待定', 'Champion': '冠军',
    'a.e.t. · penalties': '加时 · 点球', 'a.e.t. · won on pens': '加时 · 点球胜出', 'after extra time': '加时赛后',
    // live.js
    'through {d}': '截至 {d}', 'Live champion': '动态冠军',
    'Original pick — frozen at kick-off': '原始预测 —— 开赛日冻结',
    'never sees a 2026 result': '从不接触任何 2026 结果',
    'Live pick — refit through {d}': '动态预测 —— 重新拟合至 {d}',
    'real results + re-projected bracket': '真实结果 + 重新推演的对阵图',
    'Agree': '一致', 'Differ': '不同', 'Both still back': '两版都仍押', 'The update moved': '更新后改变',
    'its finalists': '其决赛双方', ', agreeing with the frozen pick': ',与冻结预测一致',
    ', a change from the frozen pick of {orig}': ',相比冻结预测的 {orig} 有所改变',
    'Both models share the same player layer and Dixon-Coles machinery; the difference is <b>information</b>. The original is a true pre-tournament forecast — it was fit only on data before 2026-06-11 and predicts its own bracket from predicted qualifiers. The <b>live</b> model is refit on every international match through <b>{d}</b>, so team ratings now carry 2026 form, and it walks the <b>real</b> bracket — the actual qualifiers and round-of-32 pairings — using real results where they exist.': '两个模型共享同一套球员层与 Dixon-Coles 机制;差别在于<b>信息</b>。原始版本是真正的赛前预测 —— 只用 2026-06-11 之前的数据拟合,并从预测的出线球队推演出自己的对阵图。<b>动态</b>模型则用截至 <b>{d}</b> 的每场国际比赛重新拟合,因此球队评分已纳入 2026 年状态,并沿<b>真实</b>对阵图 —— 实际的出线球队与 32 强对阵 —— 推进,在已有真实结果处采用真实结果。',
    'Right now the live projection has <b>{fin}</b> reaching the final and <b>{champ}</b> lifting the trophy{tail}. {n} of the projected ties are coin-flip shootouts. As more games are played, re-running the daily refresh will keep re-drawing this bracket from reality.': '目前动态推演显示 <b>{fin}</b> 闯入决赛,<b>{champ}</b> 捧杯{tail}。推演的对阵中有 {n} 场是点球对决。随着更多比赛进行,每日刷新会持续依据现实重绘这张对阵图。',
    'Error: {m}': '错误:{m}',
    // game-online.js (multiplayer) — most vocabulary is shared with game.js above
    '🎮 Prediction Game — Multiplayer': '🎮 竞猜游戏 — 多人版',
    '🔌 Not configured yet': '🔌 尚未配置',
    '🔑 Sign in to play': '🔑 登录后开玩',
    'Free, no real money. We only store a display name and your Coins.': '免费,不涉及真钱。我们只保存一个显示名和你的 Coins。',
    'Email (magic link)': '邮箱(魔法链接)',
    'Email me a sign-in link': '给我发登录链接',
    'Sign in with Google': '用 Google 登录',
    'Enter your email first.': '请先输入邮箱。',
    'Check your inbox for the sign-in link.': '登录链接已发送,请查收邮箱。',
    'Setting up your profile…': '正在创建你的档案…',
    'Signed in': '已登录',
    'sign out': '退出',
    'start 1,000': '初始 1,000',
    'Your rank': '你的排名',
    'of {n}': '共 {n}',
    '{n}/{m} settled': '{n}/{m} 已结算',
    'No players yet — be the first.': '还没有玩家 —— 来当第一个。',
    'No open ties to call right now — check back as the bracket fills in.': '暂时没有可竞猜的对阵 —— 对阵图逐步明朗后再来看看。',
    '🎯 Won · exact!': '🎯 命中 · 精确!',
    '✖ Cancelled': '✖ 已撤单',
    '(optional)': '(可选)',
    'Sign up': '注册',
    'Log in': '登录',
    'Create your account': '创建账号',
    'Welcome back': '欢迎回来',
    'Email address': '邮箱地址',
    'Email me a sign-up link': '给我发注册链接',
    'Email me a login link': '给我发登录链接',
    'Sign up with Google': '用 Google 注册',
    'Log in with Google': '用 Google 登录',
    'Already have an account?': '已有账号?',
    'New here?': '第一次来?',
    'Check your inbox to confirm and start playing.': '请查收邮箱,确认后即可开始游戏。',
    '👋 Welcome, {handle}': '👋 欢迎,{handle}',
    'You have {n} calls this tournament. Back a team to go through in any open tie below — longer odds pay more, and calling the exact score lands a much bigger bonus. Picks settle automatically as results come in.':
      '本届你有 {n} 次竞猜机会。在下方任意未开赛对阵中押一支晋级球队 —— 赔率越长赔得越多,猜中精确比分还能拿到大得多的奖励。竞猜会随真实结果自动结算。',
  };
  const KEYS = {                                 // markup subtitles carry data-i18n="..."
    'sub.index': {
      en: 'Data-driven predictions for the <b>2026 FIFA World Cup</b> — scorelines, scorers, assisters, and the whole tournament',
      zh: '数据驱动的 <b>2026 世界杯</b> 预测 —— 比分、射手、助攻,以及整届赛事',
    },
    'sub.match': {
      en: 'Predict the scoreline, scorers &amp; assisters for any <b>2026 FIFA World Cup</b> match from two starting lineups',
      zh: '从两队首发阵容预测任意一场 <b>2026 世界杯</b> 比赛的比分、射手与助攻',
    },
    'sub.tournament': {
      en: 'Every 2026 World Cup match on the single <b>most likely path</b> — 72 group games with standings, real FIFA advancement rules, and the knockout bracket to the final. Pick a group or open the bracket.',
      zh: '沿单条 <b>最可能路径</b> 预测每场 2026 世界杯比赛 —— 72 场小组赛及积分榜、真实 FIFA 晋级规则,以及通往决赛的淘汰赛对阵图。选一个小组,或打开对阵图。',
    },
    // --- Prediction Game, static in game.html (zh only; English restored from the DOM) ---
    'game.how1': { zh: "你有 <b>1,000 Coins</b> 起步。每场对阵,押你认为会 <b>晋级</b> 的一方,还可选择猜 120' 精确比分,奖励高得多。" },
    'game.how2': { zh: '<b>赔率直接来自 GoalForge 模型</b>(公平赔率 = 1 ÷ 概率):赔率越长、赔得越多,因为模型认为越不可能。' },
    'game.how3': { zh: '猜中 <b>谁晋级</b> → 按胜负赔率赔付。再猜中 <b>精确比分</b> → 按(长得多的)比分赔率赔付。' },
    'game.how4': { zh: '能猜几场取决于何时加入:<b>32 强 → 4 次</b>,16 强 → 3,8 强 → 2,半决赛 → 1。省着点用。' },
    'game.how5': { zh: '随真实结果自动结算(每日 Live 更新)。<b>🤖 模型</b> 也参与,每场押自己的选择,作为基准。' },
    'game.joinfrom': { zh: '从此轮加入' },
    'game.opt.r32': { zh: '32 强 — 4 次预测' },
    'game.opt.r16': { zh: '16 强 — 3 次预测' },
    'game.opt.qf': { zh: '8 强 — 2 次预测' },
    'game.opt.sf': { zh: '半决赛 — 1 次预测' },
    'game.reset': { zh: '↺ 重置游戏' },
    'game.footer': { zh: '一个用虚拟 Coins 的趣味游戏,仅供娱乐与演示模型,不涉及任何真钱下注。赔率为 GoalForge 模型的公平赔率;赛程与结果来自 martj42(CC0)。游戏仅保存在此浏览器(localStorage)。' },
    // --- Multiplayer game (game-online.html); zh only, English restored from the DOM ---
    'sub.game-online': { zh: '登录后用虚拟 <b>Coins</b> 与所有人同场竞技 —— 不涉及真钱。你的竞猜与排行榜是共享的,并会随真实结果自动结算。<a href="game.html">单机(免登录)版 →</a>' },
    'game-online.footer': { zh: '一个用虚拟 Coins 的趣味游戏,仅供娱乐与演示模型,不涉及任何真钱下注。赔率为 GoalForge 模型的公平赔率;结果来自 martj42(CC0)。账号与排行榜由 Supabase 提供。参见 <a href="https://github.com/aevum-orrin/GoalForge-AI/blob/main/docs/game-online-setup.md">setup</a>。' },
  };

  // ---- apply ---------------------------------------------------------------------------------
  function applyKeys(lang) {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const e = KEYS[el.getAttribute('data-i18n')];
      if (el.dataset.i18nOrig === undefined) el.dataset.i18nOrig = el.innerHTML;   // keep English source
      el.innerHTML = lang === 'zh' && e && e.zh != null ? e.zh : el.dataset.i18nOrig;
    });
  }
  function applyCM(lang) {
    document.querySelectorAll('.nav a, .grad-text, h2, .home-card p, .hc-go, .sub').forEach((el) => {
      if (el.hasAttribute('data-i18n')) return;      // handled by key
      if (el.querySelector('[id]')) return;          // contains a dynamic (#id) target — leave it
      if (el.children.length) return;                // only pure-text leaves
      if (el.dataset.i18nOrig === undefined) el.dataset.i18nOrig = el.textContent;
      const zh = DICT[norm(el.dataset.i18nOrig)];
      el.textContent = lang === 'zh' && zh != null ? zh : el.dataset.i18nOrig;
    });
  }
  function apply(lang) {
    applyKeys(lang);
    applyCM(lang);
    document.documentElement.lang = lang;
    const btn = document.querySelector('.langtoggle');
    if (btn) btn.textContent = lang === 'zh' ? 'EN' : '中文';
  }
  function setLang(lang) {
    localStorage.setItem(LANG_KEY, lang);
    apply(lang);
    document.dispatchEvent(new CustomEvent('gf:langchange', { detail: lang }));  // pages re-render dynamic text
  }
  // t(en, params): translate a dynamic string; `en` (with {placeholders}) is also the lookup key.
  function fmtT(s, p) { return p ? s.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m)) : s; }
  function t(en, p) {
    const tmpl = getLang() === 'zh' && DICT[norm(en)] != null ? DICT[norm(en)] : en;
    return fmtT(tmpl, p);
  }
  window.t = t;
  window.gfLang = getLang;

  function injectToggle() {
    const nav = document.querySelector('.nav');
    if (!nav || nav.querySelector('.langtoggle')) return;
    const b = document.createElement('button');
    b.className = 'langtoggle';
    b.type = 'button';
    b.setAttribute('aria-label', 'Switch language');
    b.addEventListener('click', () => setLang(getLang() === 'zh' ? 'en' : 'zh'));
    nav.appendChild(b);
  }
  function boot() { injectToggle(); apply(getLang()); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
