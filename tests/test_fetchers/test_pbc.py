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
      <table class="liebiao">
        <tr><td><a href="/zhengcehuobisi/125207/125217/12345/index.html" class="sxx_lm7">降准通知</a></td><td>2025-01-20</td></tr>
        <tr><td><a href="/zhengcehuobisi/125207/125217/12346/index.html" class="sxx_lm7">LPR调整公告</a></td><td>2025-01-19</td></tr>
      </table>
    </body></html>
    """
    httpx_mock.add_response(
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/11040/index1.html",
        html=html,
    )

    async with httpx.AsyncClient() as client:
        fetcher = PBCFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    titles = [a.title for a in articles]
    assert "降准通知" in titles
    assert "LPR调整公告" in titles
    for a in articles:
        assert a.source == "中国人民银行"
        assert a.category == "货币政策"
        assert a.url.startswith("http://www.pbc.gov.cn")
