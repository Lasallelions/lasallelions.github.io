// Paste into the browser pane (javascript_tool) on any page.spordle.com page.
// Defines window.__grab(id) and window.__scan(ids). Results go to window.__R (also sessionStorage '__lions_scan').
// window.__export(onlyFinalJuniorC=true) returns a compact JSON string for tools/update.py.
window.__sleep = (ms) => new Promise((r) => setTimeout(r, ms));
window.__grab = async function (id) {
  const sleep = window.__sleep;
  let f = document.getElementById('__gf'); if (f) f.remove();
  f = document.createElement('iframe'); f.id = '__gf';
  f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1200px;height:1400px';
  document.body.appendChild(f);
  f.src = '/fr/ligue-hockey-grand-montreal/schedule/' + id;
  const findH = (d) => [...d.querySelectorAll('section')].find((s) => /#\d{3,5}/.test(s.textContent) && s.querySelectorAll('h2 a[href*="/teams/"]').length === 2);
  let d, hdr;
  for (let i = 0; i < 25; i++) { await sleep(600); try { d = f.contentDocument; hdr = d && findH(d); if (hdr) break; if (i > 5 && d && / - \d/.test(d.title)) break; } catch (e) {} }
  if (!hdr) return { id, err: 'nohdr', title: d && d.title };
  const teams = [...hdr.querySelectorAll('h2 a')].map((a) => a.textContent.trim());
  const scores = [...hdr.querySelectorAll('strong')].map((s) => s.textContent.trim());
  const cat = (hdr.textContent.match(/Junior [A-Z]+|M\d+ \w+|U\d+ \w+/) || [''])[0];
  const out = { id, no: (hdr.textContent.match(/#(\d+)/) || [])[1], date: (hdr.querySelector('time') || {}).textContent, cat, teams, scores, final: /FINAL/i.test(hdr.textContent), goals: [], pens: [], lineup: {} };
  if (!out.final || !/Junior C/i.test(cat)) return out;
  // rows with their period, in document order
  const rowsOf = () => {
    const res = []; let per = '';
    const walker = d.createTreeWalker(d.querySelector('main'), NodeFilter.SHOW_ELEMENT);
    for (let n = walker.currentNode; n; n = walker.nextNode()) {
      if (n.tagName !== 'TR' && /^(\d+(re|e) P[ÉE]RIODE|PROLONGATION|TIRS DE BARRAGE)/i.test((n.textContent || '').trim()) && (n.textContent || '').trim().length < 30) per = n.textContent.trim();
      if (n.tagName === 'TR' && n.querySelector('img[alt]')) {
        res.push({ team: n.querySelector('img[alt]').alt, per, t: n.innerText.replace(/\s+/g, ' ').trim(),
          p: [...n.querySelectorAll('a[href*="/players/"]')].map((a) => [a.textContent.replace(/\(.*$/, '').trim(), a.href.split('/players/')[1]]) });
      }
    }
    return res;
  };
  for (let i = 0; i < 10; i++) { out.goals = rowsOf().filter((r) => /^\d+:\d+/.test(r.t)); if (out.goals.length || i > 6) break; await sleep(600); }
  const pt = [...d.querySelectorAll('a,button')].find((e) => e.innerText.trim() === 'Pénalités');
  if (pt) { pt.click(); for (let i = 0; i < 8; i++) { await sleep(700); const r = rowsOf().filter((r) => !/Aides/.test(r.t) && /^\d+:\d+/.test(r.t)); if (r.length) { out.pens = r; break; } } }
  const st = [...d.querySelectorAll('a,button')].find((e) => e.innerText.trim() === 'Feuille de pointage');
  if (st) {
    st.click(); let t0 = null;
    for (let k = 0; k < 2; k++) {
      let labs = [];
      for (let i = 0; i < 10; i++) { await sleep(600); labs = [...d.querySelectorAll('main label')].filter((l) => out.teams.includes(l.innerText.trim())); if (labs.length === 2) break; }
      if (labs.length < 2) { out.lerr = 'nolab'; break; }
      const lab = labs[k]; const tm = lab.innerText.trim(); lab.click();
      for (let i = 0; i < 10; i++) {
        await sleep(700);
        const rows = [...d.querySelectorAll('main tr[id*="skater"], main tr[id*="goalie"]')];
        if (!rows.length) continue;
        const tid = (rows[0].id.match(/(skater|goalie)(\d+)/) || [])[2];
        if (k === 1 && tid === t0) continue;
        if (k === 0) t0 = tid;
        out.lineup[tm] = rows.map((r) => [/goalie/.test(r.id) ? 'G' : 'S', (r.querySelector('a[href*="/players/"]') || { href: '' }).href.split('/players/')[1] || '', (r.querySelector('div[title]') || {}).title || '', ((r.querySelector('td span span') || {}).textContent || '').trim(), r.innerText.replace(/\s+/g, ' ').trim()]);
        break;
      }
    }
  } else out.lerr = 'notab';
  return out;
};
window.__R = window.__R || {};
window.__scan = function (ids, gapMs) {
  window.__done = false;
  (async () => {
    for (const id of ids) {
      let r; try { r = await window.__grab(id); } catch (e) { r = { id, err: String(e) }; }
      window.__R[id] = r;
      try { sessionStorage.setItem('__lions_scan', JSON.stringify(window.__R)); } catch (e) {}
      await window.__sleep(gapMs || 1000);
    }
    window.__done = true;
  })();
  return 'scanning ' + ids.length;
};
window.__status = () => { const v = Object.values(window.__R); return { done: !!window.__done, n: v.length, final: v.filter((x) => x.final).map((x) => x.no), err: v.filter((x) => x.err || x.lerr).map((x) => x.id + ':' + (x.err || x.lerr)) }; };
// Compact export for tools/update.py: header info for every scanned id, plus full data for final Junior C games.
window.__export = (ids) => JSON.stringify(Object.values(window.__R).filter((x) => !ids || ids.includes(x.id)).map((x) => {
  const h = { id: x.id, no: x.no, date: x.date, teams: x.teams, scores: x.scores, final: x.final, cat: x.cat, err: x.err };
  if (x.final && /Junior C/i.test(x.cat || '')) Object.assign(h, {
    goals: x.goals.map((g) => [g.team, (g.per || '').split(' ')[0], g.t.split(' ')[0], g.p.map((p) => p[1])]),
    pens: x.pens.map((g) => [g.team, (g.per || '').split(' ')[0], g.t.split(' ')[0], g.p.map((p) => p[1]), g.t.slice(g.t.indexOf(g.team) + g.team.length).trim()]),
    lineup: Object.fromEntries(Object.entries(x.lineup).map(([t, r]) => [t, r.map((z) => [z[0], z[1], z[2], z[3], z[0] === 'G' ? (/Victoire/.test(z[4]) ? 'W' : /D\u00e9faite/.test(z[4]) ? 'L' : /Nulle|\u00c9galit\u00e9/.test(z[4]) ? 'T' : '') : ''])])),
    lerr: x.lerr });
  return h;
}));
// Standings and suspensions (call on the standings page's own window or via iframe helper below)
window.__table = async function (tab) {
  let f = document.getElementById('__gf'); if (f) f.remove();
  f = document.createElement('iframe'); f.id = '__gf'; f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1400px;height:1400px'; document.body.appendChild(f);
  f.src = '/fr/ligue-hockey-grand-montreal/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?categoryId=4db0bd5f-6773-4a84-9ff6-661863a5c069&scheduleId=198712&showAdvanced=1&tab=' + tab;
  for (let i = 0; i < 30; i++) {
    await window.__sleep(800);
    try {
      const t = f.contentDocument.querySelector('main table');
      if (t && (tab !== 'standings' || /BP/.test(t.innerText)) && t.querySelectorAll('tbody tr').length) { await window.__sleep(800); return [...t.querySelectorAll('tbody tr')].map((r) => [...r.children].map((c) => c.innerText.replace(/\s+/g, ' ').trim()).join('|')).join('\n'); }
    } catch (e) {}
  }
  return 'TIMEOUT';
};
'grab.js loaded';
