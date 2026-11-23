const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 900 } });
  const errs = []; p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  
  
  await p.goto('file://' + process.argv[2]); await p.waitForTimeout(800);
  await p.screenshot({ path: 'home.png', fullPage: false });
  for (const tab of ['roster','stats','games','schedule','standings','league']) {
    await p.click(`.ll-tab[data-tab="${tab}"]`); await p.waitForTimeout(400);
    const dashes = await p.$$eval(`#${tab} [data-draw]`, els => els.filter(e => e.textContent.trim() === '—' || (e.children.length===0 && e.textContent.trim()==='' && !/sw/.test(e.dataset.draw))).map(e => e.dataset.draw));
    const svgs = await p.$$eval(`#${tab} svg`, s => s.length); const rows = await p.$$eval(`#${tab} tbody tr`, s => s.length);
    console.log(tab, 'svgs', svgs, 'rows', rows, 'empty', JSON.stringify(dashes));
    if (tab==='league' || tab==='stats') await p.screenshot({ path: tab + '.png', fullPage: true });
  }
  await p.selectOption('#lg-team', 'LIONS LASALLE'); await p.waitForTimeout(200);
  console.log('lions rows', await p.$$eval('[data-draw="lg-players"] tr', s => s.length));
  await p.setViewportSize({ width: 390, height: 800 }); await p.click('.ll-tab[data-tab="home"]'); await p.waitForTimeout(400);
  await p.screenshot({ path: 'mobile.png' });
  console.log('scrollW', await p.evaluate(() => document.documentElement.scrollWidth));
  console.log('ERRS', JSON.stringify(errs.slice(0,10)));
  await b.close();
})();
