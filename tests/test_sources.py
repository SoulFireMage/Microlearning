import pytest

from app import sources


class FakeResp:
    def __init__(self, json_data=None, text="", ctype="application/json"):
        self._j, self.text, self.headers = json_data, text, {"content-type": ctype}

    def json(self):
        return self._j


def test_wikipedia_parse(monkeypatch):
    payload = {"query": {"pages": {"123": {
        "pageid": 123, "title": "Lagrange multiplier",
        "fullurl": "https://en.wikipedia.org/wiki/Lagrange_multiplier",
        "extract": "In mathematical optimization, the method of Lagrange multipliers is a strategy for finding the local maxima and minima of a function subject to equation constraints.\n\n\n\n== Summary ==\nMore.",
    }}}}
    seen = {}
    def fake_get(url, **params):
        seen.update(params)
        return FakeResp(payload)
    monkeypatch.setattr(sources, "_get", fake_get)
    d = sources.fetch("url", "https://en.wikipedia.org/wiki/Lagrange_multiplier")
    assert seen["titles"] == "Lagrange multiplier"
    assert d.kind == "wikipedia" and d.title == "Lagrange multiplier"
    assert "\n\n\n" not in d.text
    assert sources.first_paragraph(d.text).startswith("In mathematical optimization")


def test_wikipedia_missing(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda url, **p: FakeResp({"query": {"pages": {"-1": {"title": "Zzz", "missing": ""}}}}))
    with pytest.raises(sources.SourceError):
        sources.fetch_wikipedia("Zzz")


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All
      You Need</title>
    <summary>  The dominant sequence transduction models are based on complex recurrent or
      convolutional neural networks.  </summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>"""


def test_arxiv_parse(monkeypatch):
    seen = {}
    def fake_get(url, **params):
        seen.update(params)
        return FakeResp(text=ATOM, ctype="application/atom+xml")
    monkeypatch.setattr(sources, "_get", fake_get)
    d = sources.fetch("arxiv", "https://arxiv.org/abs/1706.03762v7")
    assert seen["id_list"] == "1706.03762"
    assert d.title == "Attention Is All You Need"
    assert "Ashish Vaswani, Noam Shazeer" in d.text
    assert d.url == "https://arxiv.org/abs/1706.03762"


def test_html_extraction(monkeypatch):
    html = "<html><head><title> A Post </title><script>var x=1</script></head><body><nav>menu</nav><p>Real content here.</p><footer>foot</footer></body></html>"
    monkeypatch.setattr(sources, "_get", lambda url, **p: FakeResp(text=html, ctype="text/html; charset=utf-8"))
    d = sources.fetch_url("https://example.org/post")
    assert d.title == "A Post"
    assert "Real content here." in d.text and "menu" not in d.text and "var x" not in d.text
