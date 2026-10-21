# -*- coding: utf-8 -*-
"""外部论文数据源：OpenAlex（真实引用数）+ arXiv（最新预印本）降级。

OpenAlex 免费无 key（50000 请求/天），`filter=title.search:` 检索红外小目标领域论文，
按「引用数倒序」取高引经典 + 按「发表日期倒序」取最新论文，合并去重；
OpenAlex 不可用时降级 arXiv（无引用数，由 AI 判断）。
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import httpx

OPENALEX = "https://api.openalex.org/works"
ARXIV = "https://export.arxiv.org/api/query"
HEADERS = {"User-Agent": "Workbench-DailyPaper/1.0 (research assistant; local app)"}

# 红外小目标领域检索词（标题匹配，避免全文搜索跑偏）
QUERY = "infrared small target detection"


def _reconstruct_abstract(inverted: dict) -> str:
    """OpenAlex 的摘要按词倒排索引存储，还原为正序句子。"""
    if not inverted:
        return ""
    words = [""] * (max(max(v) for v in inverted.values()) + 1)
    for word, pos_list in inverted.items():
        for p in pos_list:
            words[p] = word
    return " ".join(words)


def _norm_title(t: str) -> str:
    return re.sub(r"[\s\-_]", "", (t or "").lower())


def _dedup(candidates: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for c in candidates:
        k = _norm_title(c.get("title", ""))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def _pdf_url_of(work: dict) -> str:
    """从 OpenAlex 条目提取可直接下载的 PDF 链接（尽力而为）。"""
    best = work.get("best_oa_location") or {}
    pdf = best.get("pdf_url") or ""
    if pdf:
        return pdf
    oa = work.get("open_access") or {}
    return oa.get("oa_url") or ""


def _search_openalex(sort: str, per_page: int = 12) -> list[dict]:
    """OpenAlex 检索。sort: cited_by_count:desc（高引）/ publication_date:desc（最新）。"""
    for _ in range(3):  # SSL 偶发 EOF，重试
        try:
            r = httpx.get(
                OPENALEX,
                params={
                    "filter": f"title.search:{QUERY}",
                    "sort": sort,
                    "per-page": per_page,
                },
                timeout=30,
                headers=HEADERS,
            )
            r.raise_for_status()
            break
        except (httpx.HTTPError, httpx.ConnectError):
            r = None
    if r is None or r.status_code != 200:
        return []
    out = []
    for w in r.json().get("results", []):
        title = (w.get("title") or "").strip()
        if not title:
            continue
        src = ((w.get("primary_location") or {}).get("source") or {})
        authors = [
            (a.get("author") or {}).get("display_name") or ""
            for a in (w.get("authorships") or [])
        ]
        authors = [a for a in authors if a]
        doi = (w.get("doi") or "").replace("https://doi.org/", "").replace("http://doi.org/", "")
        out.append(
            {
                "title": title,
                "authors": authors,
                "year": w.get("publication_year"),
                "publication": src.get("display_name") or "",
                "doi": doi,
                "url": w.get("doi") or w.get("id") or "",
                "citation_count": w.get("cited_by_count"),
                "abstract": _reconstruct_abstract(w.get("abstract_inverted_index") or {}),
                "pdf_url": _pdf_url_of(w),
                "source": "openalex",
            }
        )
    return out


def _search_arxiv(max_results: int = 15) -> list[dict]:
    """arXiv 检索红外小目标最新论文（无引用数）。"""
    try:
        r = httpx.get(
            ARXIV,
            params={
                "search_query": f'all:"{QUERY}"',
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            timeout=30,
            headers=HEADERS,
        )
        r.raise_for_status()
    except (httpx.HTTPError, httpx.ConnectError):
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return []
    for e in root.findall("a:entry", ns):
        title = re.sub(r"\s+", " ", e.findtext("a:title", "", ns) or "").strip()
        if not title:
            continue
        authors = [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]
        authors = [a for a in authors if a]
        published = e.findtext("a:published", "", ns) or ""
        year = None
        m = re.match(r"(\d{4})", published)
        if m:
            year = int(m.group(1))
        abstract = re.sub(r"\s+", " ", e.findtext("a:summary", "", ns) or "").strip()
        abs_url = e.findtext("a:id", "", ns) or ""
        pdf_url = ""
        if abs_url:
            m = re.search(r"abs/([^/]+)", abs_url)
            pdf_url = f"https://arxiv.org/pdf/{m.group(1)}.pdf" if m else ""
        out.append(
            {
                "title": title,
                "authors": authors,
                "year": year,
                "publication": "arXiv",
                "doi": "",
                "url": abs_url,
                "citation_count": None,  # arXiv 无引用数，AI 判断
                "abstract": abstract,
                "pdf_url": pdf_url,
                "source": "arxiv",
            }
        )
    return out


def fetch_candidates() -> tuple[list[dict], str]:
    """获取候选论文（去重）。返回 (candidates, source)。
    source: openalex（含真实引用数）/ arxiv（降级，无引用数）。
    """
    high = _search_openalex("cited_by_count:desc", per_page=12)
    fresh = _search_openalex("publication_date:desc", per_page=12)
    if high or fresh:
        cands = _dedup(high + fresh)
        return cands, "openalex"
    # 降级 arXiv
    arxiv = _search_arxiv()
    return _dedup(arxiv), "arxiv"


def is_recent_enough(c: dict) -> bool:
    """是否近 1-2 年（用于候选标记，最终由 AI 判断）。"""
    y = c.get("year")
    return bool(y) and y >= date.today().year - 2


def _safe_filename(title: str, max_len: int = 60) -> str:
    """清理标题为合法文件名（去掉 Windows 非法字符与首尾空白）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "", title or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:max_len].rstrip(" .") or "paper"


def download_pdf(pdf_url: str, dest_dir: Path, prefix: str = "") -> str:
    """下载论文 PDF 到 dest_dir，返回文件名；失败/非 PDF 返回空串。

    校验响应确为 PDF（content-type 或文件头 %PDF），避免把错误页/HTML 存下来。
    """
    if not pdf_url:
        return ""
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS) as client:
            with client.stream("GET", pdf_url) as resp:
                resp.raise_for_status()
                ctype = (resp.headers.get("content-type") or "").lower()
                # 限制体积（50MB 上限），防拉取异常大文件
                length = resp.headers.get("content-length")
                if length and int(length) > 50 * 1024 * 1024:
                    return ""
                # 打开方式：
                out = dest_dir / f"{prefix}.pdf"
                ok = False
                with out.open("wb") as f:
                    head = b""
                    for chunk in resp.iter_bytes(65536):
                        if len(head) < 4096:
                            head += chunk
                        f.write(chunk)
                if head[:4] == b"%PDF":
                    ok = True
                elif ctype and "pdf" in ctype:
                    ok = True
                if not ok:
                    out.unlink(missing_ok=True)
                    return ""
                return out.name
    except (httpx.HTTPError, httpx.ConnectError, OSError, ValueError):
        return ""


if __name__ == "__main__":
    # 手动验证
    cands, src = fetch_candidates()
    print("source:", src, "count:", len(cands))
    for c in cands[:8]:
        print(
            "-", c["title"][:60], "|", c.get("year"), "| cites:", c.get("citation_count"),
            "|", c.get("publication")[:30],
        )
    print("abstract sample:", cands[0]["abstract"][:100] if cands else "")