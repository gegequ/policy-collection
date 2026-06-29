// 用 Playwright 抓取指数 PE 估值数据，输出 JSON 到 stdout
const { chromium } = require('playwright');

(async () => {
  // 东方财富指数详情页（以沪深300为例）
  // quote.eastmoney.com 页面上的 PE 数据来自内嵌 API，渲染后可提取
  const url = process.argv[2];
  if (!url) {
    console.error('Usage: node fetch_pe_page.js <url>');
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    // 拦截 API 响应，提取指数估值数据
    const peData = {};

    page.on('response', async (response) => {
      const reqUrl = response.url();
      // 拦截 push2 API 返回的指数行情
      if (reqUrl.includes('push2.eastmoney.com/api/qt/stock/get') && reqUrl.includes('secid=')) {
        try {
          const body = await response.json();
          const data = body?.data;
          if (data) {
            const name = data.f58 || '';
            const price = (data.f43 || 0) / 100;
            // f115 可能是 PE，但对于指数不太准确
            const pe = data.f115;
            peData[name] = {
              price: price,
              pe_raw: pe ? parseFloat(pe) : null,
              secid: reqUrl.match(/secid=([^&]+)/)?.[1] || '',
            };
          }
        } catch (e) { /* ignore parse errors */ }
      }
    });

    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

    // 额外从页面 DOM 提取 PE 估值信息
    // 东方财富指数详情页 .valuation 等元素包含 PE 数据
    const domPe = await page.evaluate(() => {
      const result = {};
      // 尝试从页面提取 PE/PB 文本
      const allText = document.body.innerText || '';
      // 常见格式: "市盈率：14.4" / "PE(TTM)：14.4"
      const peMatch = allText.match(/(?:市盈率|PE\s*\(?TTM\)?)\s*[:：]\s*([\d.]+)/);
      if (peMatch) result.pe_ttm = parseFloat(peMatch[1]);
      const pbMatch = allText.match(/(?:市净率|PB)\s*[:：]\s*([\d.]+)/);
      if (pbMatch) result.pb = parseFloat(pbMatch[1]);
      return result;
    });

    console.log(JSON.stringify({ api: peData, dom: domPe }, null, 2));
  } catch (e) {
    console.error('ERROR:', e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
