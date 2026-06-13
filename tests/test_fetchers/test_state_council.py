# tests/test_fetchers/test_state_council.py
import pytest
import httpx
from src.fetchers.state_council import StateCouncilFetcher


def test_state_council_metadata():
    fetcher = StateCouncilFetcher()
    assert fetcher.name == "state_council"
    assert fetcher.category == "宏观决策"


@pytest.mark.asyncio
async def test_state_council_parses_list(httpx_mock):
    html = """
    <html><body>
      <div class="news_box">
        <li><a href="https://www.gov.cn/zhengce/content/202501/content_12345.htm">国务院关于促进资本市场健康发展的若干意见</a><span>2025-01-20</span></li>
        <li><a href="https://www.gov.cn/zhengce/content/202501/content_12346.htm">关于进一步优化营商环境的通知</a><span>2025-01-19</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.gov.cn/zhengce/", html=html)

    async with httpx.AsyncClient() as client:
        fetcher = StateCouncilFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    for a in articles:
        assert a.source == "国务院"
        assert a.category == "宏观决策"
        assert "www.gov.cn" in a.url
