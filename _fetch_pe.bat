@echo off
echo 正在抓取 PE 估值数据...
echo.

REM 启动浏览器
playwright-cli open

REM 乐咕乐股——大盘PE
echo [1] legulegu.com...
playwright-cli goto "https://www.legulegu.com/stockdata/market_pe" --json > data\pe_raw_1.json 2>nul

REM 东方财富——沪深300 PE
echo [2] eastmoney.com...
playwright-cli goto "https://quote.eastmoney.com/zs000300.html" 2>nul
playwright-cli eval "document.querySelector('.pe') ? document.querySelector('.pe').innerText : 'not found'" 2>nul

REM 关闭浏览器
playwright-cli close

echo.
echo Done. Check data/pe_raw_*.json
pause
