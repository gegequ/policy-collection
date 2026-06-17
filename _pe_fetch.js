const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // 用浏览器内置的 fetch 调API，绕过反爬
  const result = await page.evaluate(async () => {
    const indices = [
      '1.000300','1.000905','0.399006','1.000688','0.399986',
      '1.000932','1.000933','0.399967','0.399808','1.000819',
      '0.399393','0.399976','0.399995'
    ];
    const data = {};
    for (const secid of indices) {
      try {
        const resp = await fetch(`https://push2.eastmoney.com/api/qt/stock/get?secid=${secid}&fields=f43,f57,f58,f170,f20,f21,f115,f116,f117`);
        const json = await resp.json();
        if (json.data) {
          data[secid] = json.data;
        }
      } catch(e) {}
    }
    return data;
  });

  // 解析结果
  const names = {
    '1.000300':'沪深300','1.000905':'中证500','0.399006':'创业板指','1.000688':'科创50',
    '0.399986':'中证银行','1.000932':'中证消费','1.000933':'中证医药','0.399967':'中证军工',
    '0.399808':'中证新能源','1.000819':'有色金属','0.399393':'房地产','0.399976':'CS新能车','0.399995':'中证基建'
  };

  for (const [secid, d] of Object.entries(result)) {
    const name = names[secid] || secid;
    const price = d.f43 ? d.f43 / 100 : null;
    const pe = d.f115 || d.f20 || null;
    const pb = d.f116 || d.f21 || null;
    console.log(`${name}: price=${price?.toFixed(1)}, PE=${pe}, PB=${pb}`);
  }

  await browser.close();
  fs.writeFileSync('data/pe_api_results.json', JSON.stringify(result, null, 2));
  console.log('\nDone');
})();
