// Shared visual knockout bracket. The 2026 FIFA tree is fixed (Regulations Art. 12.7-12.11);
// listed top-to-bottom so adjacent pairs in each column merge into the next round.
// Bilingual helper `t()` is the global window.t (i18n.js); we DON'T redeclare `const t` here because
// bracket.js is always co-loaded with a page script (tournament/live/compare.js) that already declares
// it, and classic scripts share one lexical scope — a second top-level `const t` throws a redeclaration.
const BRACKET_ROUNDS = [
  ['r32', 'Round of 32', ['M74', 'M77', 'M73', 'M75', 'M83', 'M84', 'M81', 'M82',
                          'M76', 'M78', 'M79', 'M80', 'M86', 'M88', 'M85', 'M87']],
  ['r16', 'Round of 16', ['M89', 'M90', 'M93', 'M94', 'M91', 'M92', 'M95', 'M96']],
  ['qf', 'Quarter-finals', ['M97', 'M98', 'M99', 'M100']],
  ['sf', 'Semi-finals', ['M101', 'M102']],
  ['final', 'Final', ['M104']],
];

function bkTeamRow(name, score, pens, win, lose) {
  const cls = !name ? 'tbd' : (win ? 'win' : (lose ? 'lose' : ''));
  const sc = score == null ? '' : `${score}${pens != null ? `<span class="bk-pk">(${pens})</span>` : ''}`;
  return `<div class="bkteam ${cls}"><span class="bk-nm">${name || t('TBD')}</span>
    <span class="bk-sc">${sc}</span></div>`;
}

function bkMatchBox(m, champ) {
  m = m || {};
  const hw = m.winner && m.winner === m.home;
  const aw = m.winner && m.winner === m.away;
  const live = m.live && !m.winner && m.home && m.away;
  const isChamp = champ && m.winner === champ;
  const pred = m.pred && (m.home || m.away);         // live re-forecast: a predicted future tie
  const penH = m.pens ? m.pens[0] : null, penA = m.pens ? m.pens[1] : null;
  let note = '';
  if (m.decided === 'pens') note = m.pens ? t('a.e.t. · penalties') : t('a.e.t. · won on pens');
  else if (m.decided === 'aet') note = t('after extra time');
  return `<div class="bkbox ${live ? 'bk-live' : ''} ${pred ? 'bk-pred' : ''} ${isChamp ? 'bk-champ' : ''}">
    ${bkTeamRow(m.home, m.hs, penH, hw, m.winner && aw)}
    ${bkTeamRow(m.away, m.as, penA, aw, m.winner && hw)}
    ${note ? `<div class="bk-note">${note}</div>` : ''}
  </div>`;
}

// byMid: { M73: {home, away, hs, as, winner, live}, ... }.  opts: {champion, championLabel}
function renderBracket(el, byMid, opts = {}) {
  el.innerHTML = BRACKET_ROUNDS.map(([key, label, ids]) => {
    if (key === 'final') {
      const m = byMid.M104 || {};
      const champ = opts.champion || m.winner;
      return `<div class="bkcol"><div class="bkcol-h">${t(label)}</div>
        <div class="bk-final-wrap">
          ${bkMatchBox(m, champ)}
          <div class="bk-trophy">🏆</div>
          <div class="bk-champ-name"><span class="lbl">${opts.championLabel || t('Champion')}</span>${champ || t('TBD')}</div>
        </div></div>`;
    }
    return `<div class="bkcol"><div class="bkcol-h">${t(label)}</div>
      ${ids.map((id) => bkMatchBox(byMid[id], opts.champion)).join('')}</div>`;
  }).join('');
}
