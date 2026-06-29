# tests/test_fetchers/test_state_council.py
import pytest
import httpx
from src.fetchers.state_council import StateCouncilFetcher


def test_state_council_metadata():
    fetcher = StateCouncilFetcher()
    assert fetcher.name == "state_council"
    assert fetcher.category == "宏观决策"


@pytest.mark.asyncio
async def test_state_council_parses_list(httpx_mock, monkeypatch):
    # Mock Playwright 调用使其失败，触发 httpx 回退
    from src.fetchers import state_council as sc_mod
    async def mock_fetch_html_js(url, timeout=30):
        raise RuntimeError("mock: Playwright not available")
    monkeypatch.setattr(sc_mod.StateCouncilFetcher, "fetch_html_js", mock_fetch_html_js)

    html = """
    <html><body>
      <a href="/zhengce/content/202501/content_12345.htm">国务院关于促进资本市场健康发展的若干意见</a>
      <a href="/zhengce/content/202501/content_12346.htm">关于进一步优化营商环境的政策措施通知</a>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.gov.cn/zhengce/", html=html)
    # 模拟正文详情页（body + date 各请求一次，设为可复用）
    body_html = "<html><body><span class='date'>2025-01-20</span><div class='article'>为促进资本市场健康发展。</div></body></html>"
    httpx_mock.add_response(
        url="https://www.gov.cn/zhengce/content/202501/content_12345.htm",
        html=body_html, is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://www.gov.cn/zhengce/content/202501/content_12346.htm",
        html=body_html, is_reusable=True,
    )

    async with httpx.AsyncClient() as client:
        fetcher = StateCouncilFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    for a in articles:
        assert a.source == "国务院"
        assert a.category == "宏观决策"
        assert "www.gov.cn" in a.url
