// 用 Playwright 抓取 JS 渲染页面，输出 HTML 到 stdout
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2];
  if (!url) {
    console.error('Usage: node fetch_page.js <url>');
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    const html = await page.content();
    console.log(html);
  } catch (e) {
    console.error('ERROR:', e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
