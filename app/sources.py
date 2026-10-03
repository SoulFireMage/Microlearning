"""Fetch freely accessible source text to ground knowledge units.

Supported: Wikipedia (CC BY-SA), arXiv abstracts (metadata is CC0), any
public web page (crude text extraction), or pasted text. Source text is
kept with the unit so later synthesis can be grounded in it rather than in
the model's memory.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlparse

import httpx

USER_AGENT = "ThreadResilientEngine/0.1 (personal learning tool; huggingface.co Space)"
MAX_CHARS = 12000


@dataclass
class SourceDoc:
    kind: str
    title: str
    url: str | None
    text: str


class SourceError(RuntimeError):
    pass


def _get(url: str, **params) -> httpx.Response:
    try:
        r = httpx.get(
            url,
            params=params or None,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r
    except httpx.HTTPError as e:
        raise SourceError(f"Fetch failed for {url}: {e}") from e


def fetch_wikipedia(ref: str) -> SourceDoc:
    title = ref
    if ref.startswith("http"):
        title = unquote(urlparse(ref).path.rsplit("/", 1)[-1])
    title = title.replace("_", " ").strip()
    data = _get(
        "https://en.wikipedia.org/w/api.php",
        action="query",
        prop="extracts|info",
        explaintext=1,
        redirects=1,
        inprop="url",
        format="json",
        titles=title,
    ).json()
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), None)
    if not page or "missing" in page or not page.get("extract"):
        raise SourceError(f"No Wikipedia article found for '{title}'")
    text = re.sub(r"\n{3,}", "\n\n", page["extract"])
    url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}"
    return SourceDoc("wikipedia", page["title"], url, text[:MAX_CHARS])


ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)


def fetch_arxiv(ref: str) -> SourceDoc:
    m = ARXIV_ID.search(ref)
    if not m:
        raise SourceError(f"Could not find an arXiv id in '{ref}'")
    aid = m.group(1)
    xml = _get("https://export.arxiv.org/api/query", id_list=aid).text
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = ET.fromstring(xml).find("a:entry", ns)
    if entry is None or entry.find("a:title", ns) is None:
        raise SourceError(f"arXiv returned no entry for {aid}")
    title = " ".join(entry.findtext("a:title", "", ns).split())
    summary = " ".join(entry.findtext("a:summary", "", ns).split())
    authors = ", ".join(a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns))
    text = f"{title}\nAuthors: {authors}\n\nAbstract: {summary}"
    return SourceDoc("arxiv", title, f"https://arxiv.org/abs/{aid}", text[:MAX_CHARS])


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form"}

    def __init__(self) -> None:
        super().__init__()
        self.depth_skip = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth_skip += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.depth_skip:
            self.parts.append(data)


def fetch_url(url: str) -> SourceDoc:
    if not url.startswith(("http://", "https://")):
        raise SourceError("URL must start with http:// or https://")
    host = urlparse(url).netloc
    if "wikipedia.org" in host:
        return fetch_wikipedia(url)
    if "arxiv.org" in host:
        return fetch_arxiv(url)
    r = _get(url)
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise SourceError(f"Unsupported content type: {ctype or 'unknown'}")
    if "html" in ctype:
        p = _TextExtractor()
        p.feed(r.text)
        text = re.sub(r"[ \t]+", " ", "".join(p.parts))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        title = " ".join(p.title.split()) or host
    else:
        text, title = r.text, host
    return SourceDoc("url", title, url, text[:MAX_CHARS])


def from_text(text: str, title: str | None = None) -> SourceDoc:
    text = text.strip()
    if not text:
        raise SourceError("Empty text")
    return SourceDoc("text", title or text.split("\n", 1)[0][:80], None, text[:MAX_CHARS])


def fetch(kind: str, ref: str, title: str | None = None) -> SourceDoc:
    if kind == "wikipedia":
        return fetch_wikipedia(ref)
    if kind == "arxiv":
        return fetch_arxiv(ref)
    if kind == "url":
        return fetch_url(ref)
    if kind == "text":
        return from_text(ref, title)
    raise SourceError(f"Unknown source kind '{kind}'")


def first_paragraph(text: str, max_words: int = 70) -> str:
    for para in text.split("\n"):
        para = para.strip()
        if len(para.split()) >= 12:
            words = para.split()
            return " ".join(words[:max_words]) + (" …" if len(words) > max_words else "")
    return " ".join(text.split()[:max_words])
