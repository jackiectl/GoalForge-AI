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
  const CM = {                                   // content-matched leaves: English -> 中文
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
  };

  // ---- apply ---------------------------------------------------------------------------------
  function applyKeys(lang) {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const e = KEYS[el.getAttribute('data-i18n')];
      if (e) el.innerHTML = lang === 'zh' ? e.zh : e.en;
    });
  }
  function applyCM(lang) {
    document.querySelectorAll('.nav a, .grad-text, h2, .home-card p, .hc-go, .sub').forEach((el) => {
      if (el.hasAttribute('data-i18n')) return;      // handled by key
      if (el.querySelector('[id]')) return;          // contains a dynamic (#id) target — leave it
      if (el.children.length) return;                // only pure-text leaves
      if (el.dataset.i18nOrig === undefined) el.dataset.i18nOrig = el.textContent;
      const zh = CM[norm(el.dataset.i18nOrig)];
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
  function setLang(lang) { localStorage.setItem(LANG_KEY, lang); apply(lang); }

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
