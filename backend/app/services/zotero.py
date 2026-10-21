import json
from pathlib import Path

import httpx

from ..config import ZOTERO_API_URL, ZOTERO_LOCAL_URL
from ..database import SessionLocal
from ..models import Setting
from . import secure


def _get_creds():
    db = SessionLocal()
    try:
        key = db.get(Setting, "zotero_api_key")
        uid = db.get(Setting, "zotero_user_id")
        return secure.decrypt_str(key.value if key else ""), (uid.value if uid else "") or ""
    finally:
        db.close()


def is_running() -> bool:
    """本地 Zotero 桌面版是否运行（用于状态提示）。"""
    try:
        r = httpx.get(f"{ZOTERO_LOCAL_URL}/connector/ping", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def is_configured() -> bool:
    """是否已配置在线同步所需的 Key 和 User ID。"""
    key, uid = _get_creds()
    return bool(key and uid)


def get_items(limit: int = 100, max_items: int = 2000):
    """通过 Zotero 在线 API 分页读取文献条目（拉取全量）。"""
    key, uid = _get_creds()
    if not uid:
        raise ValueError("未配置 Zotero User ID，请在设置页填写")
    headers = {"Zotero-API-Key": key} if key else {}
    url = f"{ZOTERO_API_URL}/users/{uid}/items"
    out = []
    start = 0
    while start < max_items:
        r = httpx.get(
            url, headers=headers, params={"limit": limit, "start": start, "format": "json"}, timeout=20
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        start += len(batch)
        if len(batch) < limit:
            break
    return out


def get_collections() -> list[dict]:
    """读取 Zotero 集合列表。"""
    key, uid = _get_creds()
    if not uid:
        raise ValueError("未配置 Zotero User ID，请在设置页填写")
    headers = {"Zotero-API-Key": key} if key else {}
    url = f"{ZOTERO_API_URL}/users/{uid}/collections"
    r = httpx.get(url, headers=headers, params={"limit": 100, "format": "json"}, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json():
        if not isinstance(it, dict):
            continue
        data = it.get("data") or {}
        out.append(
            {
                "key": it.get("key", ""),
                "name": data.get("name", ""),
                "parent_key": data.get("parentCollection") or None,
            }
        )
    return out


def parse_items(raw: list[dict]) -> list[dict]:
    """把 Zotero item 简化为统一结构。"""
    out = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        data = it.get("data") or it
        if not isinstance(data, dict):
            continue
        item_type = data.get("itemType", "")
        # 跳过附件、笔记、批注等非文献条目
        if item_type in ("attachment", "note", "annotation"):
            continue
        title = data.get("title") or data.get("name") or "无标题"
        year = None
        date_str = data.get("date") or ""
        if len(date_str) >= 4 and date_str[:4].isdigit():
            year = int(date_str[:4])
        creators = data.get("creators") or []
        authors = []
        for c in creators[:3]:
            # Zotero 用 name 字段（机构/个人），或 firstName+lastName
            name = (c.get("name") or f"{c.get('firstName','')} {c.get('lastName','')}".strip()).strip()
            if name:
                authors.append(name)
        tags = ",".join(t.get("tag", "") for t in (data.get("tags") or []))
        out.append(
            {
                "zotero_key": it.get("key", ""),
                "zotero_version": it.get("version"),
                "title": title,
                "authors": authors,
                "year": year,
                "publication": data.get("publicationTitle") or data.get("publisher") or "",
                "item_type": item_type,
                "abstract": data.get("abstractNote") or "",
                "tags": tags,
                "collection_keys": ",".join(data.get("collections") or []),
                "url": data.get("url") or "",
                "doi": data.get("DOI") or "",
            }
        )
    return out


# ---------- 写入能力：把条目推送到用户 Zotero 库 ----------

def _require_creds():
    key, uid = _get_creds()
    if not uid:
        raise ValueError("未配置 Zotero User ID，请在设置页填写")
    if not key:
        raise ValueError("未配置 Zotero API Key，请在设置页填写")
    return key, uid


def parse_write_error(resp_json) -> str:
    """从 Zotero 写接口返回体提取失败原因（HTTP 200 也可能 failed）。"""
    failed = (resp_json or {}).get("failed") or {}
    for v in failed.values():
        if isinstance(v, dict) and v.get("message"):
            return str(v["message"])
    return ""


def _first_key(resp_json) -> str:
    """解析 Zotero 写接口返回体，取成功创建的第一个 key；失败则抛带详情错误。"""
    data = resp_json or {}
    succ = data.get("successful") or {}
    if "0" in succ and succ["0"].get("key"):
        return succ["0"]["key"]
    failed = data.get("failed") or {}
    detail = parse_write_error(data) or json.dumps(failed, ensure_ascii=False)
    raise ValueError(f"Zotero 写入失败：{detail}")


def ensure_collection(name: str) -> str:
    """按名称查找 Zotero 集合（全量拉取），找不到则创建同名集合，返回其 key。"""
    key, uid = _require_creds()
    headers = {"Zotero-API-Key": key}
    url = f"{ZOTERO_API_URL}/users/{uid}/collections"
    start = 0
    while start < 1000:
        r = httpx.get(
            url, headers=headers, params={"limit": 100, "start": start, "format": "json"}, timeout=20
        )
        r.raise_for_status()
        batch = r.json() or []
        for it in batch:
            data = it.get("data") or {}
            if data.get("name") == name:
                return it.get("key", "")
        if len(batch) < 100:
            break
        start += len(batch)
    r = httpx.post(url, headers=headers, json=[{"name": name}], timeout=20)
    r.raise_for_status()
    return _first_key(r.json())


def creators_from_names(authors) -> list[dict]:
    """工作台作者字符串列表（如 ["Bo Li", "李波"]）→ Zotero creators JSON。

    拆分规则：含逗号的按「姓, 名」拆（Li, Bo → Li / Bo）；
    无逗号的按空格拆（Bo Li → firstName=Bo / lastName=Li）；单段（中文名/机构名）只给 lastName。
    Zotero 校验要求 lastName 与 firstName 必须同时出现（firstName 可为空串），
    缺失 firstName 键会报「'firstName' creator field must be set if 'lastName' is set」。
    """
    out = []
    for raw in authors or []:
        text = str(raw).strip()
        if not text:
            continue
        if "," in text:
            last_part, _, first_part = text.partition(",")
            last, first = last_part.strip(), first_part.strip()
        else:
            parts = text.split()
            last, first = parts[-1], " ".join(parts[:-1])
        if not last:
            continue
        out.append({"creatorType": "author", "lastName": last, "firstName": first})
    return out[:25]


def build_paper_item(
    *,
    title: str,
    authors=None,
    year=None,
    publication: str = "",
    doi: str = "",
    url: str = "",
    abstract: str = "",
    tags=None,
    item_type: str = "journalArticle",
    collection_key: str = "",
) -> dict:
    """构建 Zotero 条目 JSON（journalArticle / conferencePaper）。"""
    item = {
        "itemType": item_type,
        "title": title or "无标题",
        "creators": creators_from_names(authors),
        "date": str(year) if year else "",
        "tags": [{"tag": t} for t in (tags or []) if t],
        "url": url or "",
        "abstractNote": abstract or "",
    }
    if doi:
        item["DOI"] = doi
    if publication:
        if item_type == "conferencePaper":
            item["conferenceName"] = publication
        elif item_type == "preprint":
            # 预印本没有 publicationTitle 字段（会被 Zotero 拒收），用 repository
            item["repository"] = publication
        else:
            item["publicationTitle"] = publication
    if collection_key:
        item["collections"] = [collection_key]
    return item


def push_item(item: dict) -> str:
    """POST /users/{uid}/items 创建条目（题录元数据），返回条目 key。"""
    key, uid = _require_creds()
    headers = {"Zotero-API-Key": key}
    r = httpx.post(
        f"{ZOTERO_API_URL}/users/{uid}/items",
        headers=headers,
        json=[item],
        timeout=60,
    )
    r.raise_for_status()
    return _first_key(r.json())


def _delete_item_quiet(item_key: str) -> None:
    """尽力删除 Zotero 条目（用于上传失败后清理空附件），失败静默。"""
    try:
        k, uid = _require_creds()
        h = {"Zotero-API-Key": k}
        r = httpx.get(f"{ZOTERO_API_URL}/users/{uid}/items/{item_key}", headers=h, timeout=20)
        if r.status_code != 200:
            return
        version = r.json().get("version")
        httpx.delete(
            f"{ZOTERO_API_URL}/users/{uid}/items/{item_key}",
            headers={**h, "If-Unmodified-Since-Version": str(version)},
            timeout=20,
        )
    except Exception:
        pass


def push_pdf_attachment(parent_key: str, pdf_path) -> str:
    """把 PDF 文件作为附件（imported_file）挂到条目下，返回附件 key。

    按 Zotero 官方文件上传流程（Web API v3 File Uploads）：
    ① POST /items 创建附件条目（md5/mtime 留空，由服务器回填）；
    ② POST /items/{key}/file（If-None-Match: * + md5/filename/filesize/mtime）申请上传授权：
       返回 `{"exists": 1}` 表示服务器已有该文件并已关联，直接完成；
    ③ 否则把 prefix + 文件内容 + suffix POST 到授权 url（Content-Type=authorization.contentType），
       再带 uploadKey 调一次 /file 注册。
    失败时尽力删除刚创建的空附件条目，避免库中留下无文件的附件。
    """
    import hashlib

    key, uid = _require_creds()
    headers = {"Zotero-API-Key": key}
    path = Path(pdf_path)
    data = path.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    mtime = int(path.stat().st_mtime * 1000)
    att = {
        "itemType": "attachment",
        "parentItem": parent_key,
        "linkMode": "imported_file",
        "title": path.name,
        "contentType": "application/pdf",
        "filename": path.name,
    }
    r = httpx.post(f"{ZOTERO_API_URL}/users/{uid}/items", headers=headers, json=[att], timeout=60)
    r.raise_for_status()
    att_key = _first_key(r.json())
    try:
        auth = httpx.post(
            f"{ZOTERO_API_URL}/users/{uid}/items/{att_key}/file",
            headers={**headers, "If-None-Match": "*"},
            data={"md5": md5, "filename": path.name, "filesize": str(len(data)), "mtime": str(mtime)},
            timeout=60,
        )
        auth.raise_for_status()
        info = auth.json() or {}
        if info.get("exists"):
            return att_key  # 服务器已有该文件，已关联完成
        url = info.get("url")
        if not url:
            raise ValueError(f"Zotero 未返回上传地址：{info}")
        prefix = (info.get("prefix") or "").encode()
        suffix = (info.get("suffix") or "").encode()
        content_type = info.get("contentType") or "application/octet-stream"
        up = httpx.post(
            url, content=prefix + data + suffix, headers={"Content-Type": content_type}, timeout=300
        )
        up.raise_for_status()
        reg = httpx.post(
            f"{ZOTERO_API_URL}/users/{uid}/items/{att_key}/file",
            headers={**headers, "If-None-Match": "*"},
            data={"upload": info.get("uploadKey") or ""},
            timeout=60,
        )
        reg.raise_for_status()
        return att_key
    except Exception:
        _delete_item_quiet(att_key)
        raise


def find_pdf_attachment(parent_key: str) -> str:
    """查找条目下已有的 PDF 附件 key（避免重复挂同一文件），没有则返回空串。"""
    key, uid = _require_creds()
    r = httpx.get(
        f"{ZOTERO_API_URL}/users/{uid}/items/{parent_key}/children",
        headers={"Zotero-API-Key": key},
        params={"limit": 100},
        timeout=30,
    )
    r.raise_for_status()
    for it in r.json() or []:
        data = it.get("data") or {}
        if data.get("itemType") != "attachment":
            continue
        ctype = (data.get("contentType") or "").lower()
        fname = (data.get("filename") or "").lower()
        if "pdf" in ctype or fname.endswith(".pdf"):
            return it.get("key", "")
    return ""


def get_item(key: str) -> dict:
    """读取单个 Zotero 条目（含 version / data），更新标签前必须先拿到当前 version。"""
    k, uid = _require_creds()
    r = httpx.get(
        f"{ZOTERO_API_URL}/users/{uid}/items/{key}",
        headers={"Zotero-API-Key": k},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def update_item_tags(key: str, add=None, remove=None, collection_key: str = "") -> dict:
    """在已有 Zotero 条目上增删标签 / 补集合归属（幂等）。

    Zotero 修改条目需带上当前 version（乐观锁），所以先 GET 再 PUT。
    `add`/`remove` 为标签字符串列表；重复标签不会重复添加。
    `collection_key` 非空且条目不在该集合时顺带加入。
    """
    k, uid = _require_creds()
    item = get_item(key)
    data = dict(item.get("data") or {})
    tags = list(data.get("tags") or [])
    remove_set = {str(t) for t in (remove or [])}
    if remove_set:
        tags = [t for t in tags if str(t.get("tag")) not in remove_set]
    existing = {str(t.get("tag")) for t in tags}
    for t in add or []:
        t = str(t)
        if t and t not in existing:
            tags.append({"tag": t})
            existing.add(t)
    data["tags"] = tags
    if collection_key:
        cols = list(data.get("collections") or [])
        if collection_key not in cols:
            cols.append(collection_key)
            data["collections"] = cols
    payload = {"key": key, "version": item.get("version"), "data": data}
    r = httpx.put(
        f"{ZOTERO_API_URL}/users/{uid}/items/{key}",
        headers={"Zotero-API-Key": k, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    # 成功更新返回 204 No Content（无响应体），不能直接 r.json()
    if r.status_code == 204 or not r.content:
        return {}
    return r.json()
