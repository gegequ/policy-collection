# tests/test_fetchers/test_ndrc.py
import pytest
import httpx
from src.fetchers.ndrc import NDRCFetcher


def test_ndrc_metadata():
    f = NDRCFetcher()
    assert f.name == "ndrc"
    assert f.category == "产业政策"


@pytest.mark.asyncio
async def test_ndrc_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="u-list">
        <li><a href="/xwzx/xwtt/202501/t20250120_12345.html">关于推动能源高质量发展的指导意见</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.ndrc.gov.cn/xwzx/xwtt/", html=html)

    async with httpx.AsyncClient() as client:
        articles = await NDRCFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "国家发改委"
    assert "能源" in articles[0].title
