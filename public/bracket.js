// Shared visual knockout bracket. The 2026 FIFA tree is fixed (Regulations Art. 12.7-12.11);
// listed top-to-bottom so adjacent pairs in each column merge into the next round.
const BRACKET_ROUNDS = [
  ['r32', 'Round of 32', ['M74', 'M77', 'M73', 'M75', 'M83', 'M84', 'M81', 'M82',
                          'M76', 'M78', 'M79', 'M80', 'M86', 'M88', 'M85', 'M87']],
  ['r16', 'Round of 16', ['M89', 'M90', 'M93', 'M94', 'M91', 'M92', 'M95', 'M96']],
  ['qf', 'Quarter-finals', ['M97', 'M98', 'M99', 'M100']],
  ['sf', 'Semi-finals', ['M101', 'M102']],
  ['final', 'Final', ['M104']],
];

function bkTeamRow(name, score, win, lose) {
  const cls = !name ? 'tbd' : (win ? 'win' : (lose ? 'lose' : ''));
  return `<div class="bkteam ${cls}"><span class="bk-nm">${name || 'TBD'}</span>
    <span class="bk-sc">${score == null ? '' : score}</span></div>`;
}

function bkMatchBox(m, champ) {
  m = m || {};
  const hw = m.winner && m.winner === m.home;
  const aw = m.winner && m.winner === m.away;
  const live = m.live && !m.winner && m.home && m.away;
  const isChamp = champ && m.winner === champ;
  return `<div class="bkbox ${live ? 'bk-live' : ''} ${isChamp ? 'bk-champ' : ''}">
    ${bkTeamRow(m.home, m.hs, hw, m.winner && aw)}
    ${bkTeamRow(m.away, m.as, aw, m.winner && hw)}
  </div>`;
}

// byMid: { M73: {home, away, hs, as, winner, live}, ... }.  opts: {champion, championLabel}
function renderBracket(el, byMid, opts = {}) {
  el.innerHTML = BRACKET_ROUNDS.map(([key, label, ids]) => {
    if (key === 'final') {
      const m = byMid.M104 || {};
      const champ = opts.champion || m.winner;
      return `<div class="bkcol"><div class="bkcol-h">${label}</div>
        <div class="bk-final-wrap">
          ${bkMatchBox(m, champ)}
          <div class="bk-trophy">🏆</div>
          <div class="bk-champ-name"><span class="lbl">${opts.championLabel || 'Champion'}</span>${champ || 'TBD'}</div>
        </div></div>`;
    }
    return `<div class="bkcol"><div class="bkcol-h">${label}</div>
      ${ids.map((id) => bkMatchBox(byMid[id], opts.champion)).join('')}</div>`;
  }).join('');
}
