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
    httpx_mock.add_response(url="https://www.ndrc.gov.cn/xwdt/xwfb/", html=html)
    # 模拟正文详情页（body + date 各请求一次，设为可复用）
    httpx_mock.add_response(
        url="https://www.ndrc.gov.cn/xwzx/xwtt/202501/t20250120_12345.html",
        html="<html><body><span id='con_time'>发布时间：2025-01-20 10:00</span><div class='article-content'><p>为深入贯彻落实能源安全新战略，推动能源高质量发展，现提出以下意见。加快规划建设新型能源体系。</p></div></body></html>",
        is_reusable=True,
    )

    async with httpx.AsyncClient() as client:
        articles = await NDRCFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "国家发改委"
    assert "能源" in articles[0].title
