# tests/test_fetchers/test_pbc.py
import pytest
import httpx
from src.fetchers.pbc import PBCFetcher


def test_pbc_fetcher_has_correct_metadata():
    fetcher = PBCFetcher()
    assert fetcher.name == "pbc"
    assert fetcher.category == "货币政策"


@pytest.mark.asyncio
async def test_pbc_parses_html_correctly(httpx_mock):
    html = """
    <html><body>
      <a href="/goutongjiaoliu/113456/113469/2026062215562764028/index.html">中国人民银行 金融监管总局 全国妇联印发通知 进一步支持妇女就业创业</a>
      <a href="/goutongjiaoliu/113456/113469/2026062211021396080/index.html">2026年5月金融市场运行情况</a>
      <a href="https://beian.miit.gov.cn">京ICP备05073439号</a>
    </body></html>
    """
    httpx_mock.add_response(
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        html=html,
    )
    # 模拟正文详情页（body + date 各请求一次，设为可复用）
    body_html = "<html><body><span id='con_time'>发布时间：2026-06-22</span><div class='content'>央行决定下调存款准备金率0.5个百分点。</div></body></html>"
    httpx_mock.add_response(
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026062215562764028/index.html",
        html=body_html, is_reusable=True,
    )
    httpx_mock.add_response(
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026062211021396080/index.html",
        html=body_html, is_reusable=True,
    )

    async with httpx.AsyncClient() as client:
        fetcher = PBCFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    titles = [a.title for a in articles]
    assert any("妇女就业创业" in t for t in titles)
    assert any("金融市场运行" in t for t in titles)
    for a in articles:
        assert a.source == "中国人民银行"
        assert a.category == "货币政策"
        assert a.url.startswith("http://www.pbc.gov.cn")
