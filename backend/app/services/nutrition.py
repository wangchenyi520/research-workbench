# -*- coding: utf-8 -*-
"""饮品营养联网检索（best-effort，只读、不阻塞）：

1) Open Food Facts：包装饮品的真实营养数据（免费无 key，含中文产品；偶发 503 会重试）；
2) DuckDuckGo Lite：网页搜索结果 snippet（现制奶茶/咖啡没有公开营养库，取网络资料给 AI 参考）；
3) Bing RSS：备用搜索通道（仅在前两路都无结果时尝试）。

任何通道失败都静默跳过（返回空列表），最终由 DeepSeek 结合模型知识估算。
"""
import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import httpx

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
_TIMEOUT = 5.0


def _clean(s: str) -> str:
    """去 HTML 标签 + 反转义 + 折叠空白。"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _num(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def _off_lookup(name: str) -> list[str]:
    """Open Food Facts 产品库（包装饮品的真实营养数据）。"""
    r = None
    for _ in range(2):  # 偶发 503 / SSL，重试一次
        try:
            r = httpx.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "search_terms": name,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": 4,
                    "fields": "product_name,brands,quantity,nutriments",
                },
                timeout=_TIMEOUT,
                headers=_UA,
                follow_redirects=True,
            )
            if r.status_code == 200:
                break
        except Exception:
            r = None
    if r is None or r.status_code != 200:
        return []
    try:
        products = r.json().get("products") or []
    except Exception:
        return []
    out = []
    for p in products[:4]:
        n = p.get("nutriments") or {}
        kcal = _num(n, "energy-kcal_100ml", "energy-kcal_100g")
        sugar = _num(n, "sugars_100ml", "sugars_100g")
        fat = _num(n, "fat_100ml", "fat_100g")
        if kcal is None and sugar is None and fat is None:
            continue
        label = " ".join(x for x in [p.get("brands"), p.get("product_name")] if x).strip()
        if not label:
            continue
        qty = f"（{p.get('quantity')}）" if p.get("quantity") else ""
        parts = []
        if kcal is not None:
            parts.append(f"能量 {round(kcal)}kcal")
        if sugar is not None:
            parts.append(f"糖 {sugar}g")
        if fat is not None:
            parts.append(f"脂肪 {fat}g")
        out.append(f"食品库产品：{label}{qty}，每100ml：{' / '.join(parts)}")
    return out[:4]


def _ddg_find(text: str, cls: str) -> list[str]:
    """提取 DDG Lite 结果中指定 class 的文本（quote 可能是单引号或双引号）。"""
    pat = r"class=[\'\"]" + re.escape(cls) + r"[\'\"][^>]*>(.*?)</(?:a|td)>"
    return [_clean(m.group(1)) for m in re.finditer(pat, text, re.S)]


def _ddg_lookup(name: str) -> list[str]:
    """DuckDuckGo Lite 网页搜索（中文质量好、无 key）。"""
    r = httpx.get(
        "https://lite.duckduckgo.com/lite/",
        params={"q": f"{name} 热量 糖分"},
        timeout=_TIMEOUT,
        headers=_UA,
        follow_redirects=True,
    )
    if r.status_code != 200:
        return []
    links = _ddg_find(r.text, "result-link")[:6]
    snips = _ddg_find(r.text, "result-snippet")[:6]
    out = []
    for i, s in enumerate(snips[:4]):
        title = links[i] if i < len(links) else ""
        text = f"{title} — {s}" if title else s
        if text.strip(" —"):
            out.append(f"网络资料：{text[:300]}")
    if not out:
        for t in links[:3]:
            if t:
                out.append(f"网络资料：{t[:200]}")
    return out


def _bing_lookup(name: str) -> list[str]:
    """Bing RSS 备用通道（XML 结构化结果）。"""
    r = httpx.get(
        "https://www.bing.com/search",
        params={"q": f"「{name}」 热量 糖分", "format": "rss"},
        timeout=_TIMEOUT,
        headers=_UA,
        follow_redirects=True,
    )
    if r.status_code != 200 or "<rss" not in r.text[:500]:
        return []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return []
    out = []
    for it in list(root.iter("item"))[:4]:
        t = _clean(it.findtext("title") or "")
        d = _clean(it.findtext("description") or "")
        text = f"{t} — {d}" if t else d
        if text.strip(" —"):
            out.append(f"网络资料：{text[:300]}")
    return out


def search_drink_info(name: str) -> tuple[list[str], str]:
    """检索饮品营养资料，返回 (snippets, source)。

    source：food_db=食品数据库命中 / web=网页检索命中 / ''=无结果。
    通道总体预算约 5~12 秒（前两路并行），全部失败不影响调用方。
    """
    name = (name or "").strip()
    if not name:
        return [], ""
    snippets: list[str] = []
    source = ""
    # 前两路并行；任一命中即可
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_off = ex.submit(_off_lookup, name)
        f_ddg = ex.submit(_ddg_lookup, name)
        try:
            got_off = f_off.result(timeout=_TIMEOUT + 3)
        except Exception:
            got_off = []
        try:
            got_ddg = f_ddg.result(timeout=_TIMEOUT + 3)
        except Exception:
            got_ddg = []
    if got_off:
        snippets.extend(got_off)
        source = "food_db"
    if got_ddg:
        snippets.extend(got_ddg)
        source = source or "web"
    if not snippets:  # 两路都空才试备用通道
        try:
            got_bing = _bing_lookup(name)
        except Exception:
            got_bing = []
        if got_bing:
            snippets.extend(got_bing)
            source = "web"
    return snippets[:8], source
