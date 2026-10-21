import json
import re
import time

import httpx

from ..config import DEEPSEEK_BASE_URL
from ..database import SessionLocal
from ..models import Setting
from . import secure

MODEL = "deepseek-chat"


class AIError(Exception):
    """AI 调用错误，携带友好的 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _get_key() -> str:
    db = SessionLocal()
    try:
        s = db.get(Setting, "deepseek_api_key")
        return secure.decrypt_str(s.value if s else "")
    finally:
        db.close()


def is_configured() -> bool:
    return bool(_get_key())


def chat(
    messages: list[dict],
    system: str = "你是研究生的科研助手，回复简洁、结构化、使用中文。",
    temperature: float = 0.4,
) -> str:
    """调用 DeepSeek，带重试与友好错误处理。"""
    key = _get_key()
    if not key:
        raise AIError("未配置 DeepSeek API Key，请在设置页填写。")
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": temperature,
    }
    max_retries = 2
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if not content:
                raise AIError("AI 未返回内容，请重试")
            return content
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise AIError("AI 请求超时，请稍后重试", 504)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 401:
                raise AIError("API Key 无效或已过期，请在设置页检查", 400)
            if code == 402:
                raise AIError("DeepSeek 账户余额不足，请充值", 400)
            if code == 429:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise AIError("AI 请求过于频繁，请稍后再试", 429)
            if code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise AIError("AI 服务暂时不可用，请稍后重试", 503)
            raise AIError(f"AI 服务错误（{code}），请稍后重试", 400)
        except httpx.RequestError:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise AIError("无法连接 AI 服务，请检查网络", 400)
        except (KeyError, IndexError, TypeError, ValueError):
            raise AIError("AI 返回格式异常，请重试", 400)


def summarize_text(text: str) -> str:
    system = (
        "你是科研论文阅读助手。请用中文对以下内容做结构化总结，格式："
        "【核心观点】\n【方法】\n【结论】\n【我的思考】。控制在500字内。"
    )
    return chat([{"role": "user", "content": text}], system, temperature=0.2)


def assist_writing(prompt: str, note_context: str = "") -> str:
    system = (
        "你是研究生论文写作助手，基于用户提供的笔记草稿辅助写作。"
        "严格按用户指令执行（润色/扩写/翻译/续写/总结等），"
        "输出直接是结果内容，不要额外解释。使用中文。"
    )
    content = prompt
    if note_context:
        content = f"当前笔记内容：\n{note_context}\n\n用户指令：{prompt}"
    return chat([{"role": "user", "content": content}], system, temperature=0.6)


def review_advice(week_summary: str, review_content: str = "") -> str:
    system = (
        "你是研究生的科研复盘教练。根据用户本周统计数据与复盘内容，"
        "用中文给出具体可执行的改进建议（最多6条，每条一行，用 - 开头）。"
        "语气真诚、具体，避免空话套话。"
    )
    content = f"本周统计：\n{week_summary}\n\n我的复盘内容：\n{review_content or '（未填写）'}"
    return chat([{"role": "user", "content": content}], system, temperature=0.5)


def literature_qa(question: str, context: str) -> str:
    system = (
        "你是研究生文献助手。基于提供的文献库摘要回答用户问题。"
        "如果文献库中没有相关信息，请如实说明，不要编造。"
        "用中文回答，尽量引用文献标题。回答控制在400字内。"
    )
    content = f"文献库摘要：\n{context}\n\n用户问题：{question}"
    return chat([{"role": "user", "content": content}], system, temperature=0.2)


def kb_qa(question: str, context: str) -> str:
    system = (
        "你是研究生的本地知识库问答助手。基于用户自己的笔记、文献和实验记录回答。"
        "只依据提供的内容作答，不要编造；回答时在引用处标注【来源N】。"
        "如果内容不足以回答，请如实说明。使用中文，回答控制在500字内。"
    )
    content = f"本地知识库内容：\n{context}\n\n用户问题：{question}"
    return chat([{"role": "user", "content": content}], system, temperature=0.2)


# ---------- 论文写作流水线 ----------
def paper_outline(title: str, direction: str, notes: str = "") -> str:
    system = (
        "你是学术论文写作导师。根据论文主题生成一份中文学术论文章节大纲。"
        "输出 Markdown 格式，包含：引言、相关工作、方法、实验与结果、结论 等章节，"
        "每章下列出 2-4 个要点（具体到红外小目标/计算机视觉任务应写什么），"
        "并给出写作顺序建议与每章预期字数。使用中文。"
    )
    content = f"论文主题：{title}\n研究方向：{direction or '（未填写）'}\n现有备注：{notes or '（无）'}"
    return chat([{"role": "user", "content": content}], system, temperature=0.4)


def paper_chapter(title: str, chapter: str, notes: str = "", references: str = "") -> str:
    system = (
        "你是学术论文写作助手。针对给定论文章节撰写中文学术初稿。"
        "要求：表述严谨、术语准确、有逻辑衔接；可结合提供的参考资料与文献条目组织内容；"
        "输出就是可直接编辑的段落文本，不要额外解释。"
    )
    content = (
        f"论文主题：{title}\n当前写作章节：{chapter}\n"
        f"论文备注：{notes or '（无）'}\n"
        f"参考资料：\n{references or '（无）'}"
    )
    return chat([{"role": "user", "content": content}], system, temperature=0.6)


def paper_polish(text: str, mode: str = "polish") -> str:
    system = (
        "你是学术论文润色助手。根据用户指定的模式处理论文文字，输出处理后的结果文本，不要额外解释。"
        "模式说明：polish=学术润色（更严谨/简洁/规范）；translate_en=中译英（学术英文）；translate_zh=英译中。"
    )
    label = {"polish": "学术润色", "translate_en": "翻译为学术英文", "translate_zh": "翻译为中文"}.get(mode, "学术润色")
    return chat([{"role": "user", "content": f"请对以下论文文字进行{label}：\n\n{text}"}], system, temperature=0.4)


def organize_note(content: str) -> str:
    system = (
        "你是科研笔记整理助手。将用户杂乱的笔记整理为结构化内容，"
        "输出格式：【核心主题】【要点】【结论/收获】【待办/疑问】。"
        "保留原文信息，使用中文，简洁。"
    )
    return chat([{"role": "user", "content": content}], system, temperature=0.3)


def meeting_notes(text: str) -> str:
    system = (
        "你是学术会议纪要助手。将用户提供的会议/组会内容整理为结构化纪要，"
        "输出格式：【会议主题】【讨论要点】【结论与决定】【行动项】。"
        "使用中文，简洁清晰。"
    )
    return chat([{"role": "user", "content": text}], system, temperature=0.4)


def tag_literature(title: str, abstract: str) -> str:
    system = (
        "你是文献分类助手。根据文献标题和摘要，给出 3-6 个中文标签，"
        "用中文顿号或逗号分隔，只输出标签本身，不要任何解释文字。"
    )
    content = f"标题：{title}\n摘要：{abstract[:800] or '（无摘要）'}"
    return chat([{"role": "user", "content": content}], system, temperature=0.1)


def journal_info(publication: str) -> dict:
    """根据期刊/会议名推断中科院分区与影响因子。返回 {"level":..., "if":...}，不确定则空。"""
    system = (
        "你是学术期刊信息助手。根据给出的期刊/会议名称，输出它的中科院分区（如「中科院二区」「CCF-A」）"
        "和影响因子（如 5.8，无则留空）。只输出 JSON 对象，不要解释："
        '{"level":"分区或等级(字符串,不确定可空)","if":"影响因子数字(字符串,无则空字符串)"}。'
        "注意：AI 推断仅供投稿参考，无法保证绝对准确。"
    )
    raw = _ai_json(system, f"期刊/会议：{publication}", temperature=0.1)
    if not isinstance(raw, dict):
        return {}
    return {
        "level": str(raw.get("level") or "").strip()[:40],
        "if": str(raw.get("if") or "").strip()[:20],
    }


# ---------- AI 规划助手 ----------
_PLAN_SCHEMA = """{
  "annual": {"title": "年度目标标题", "description": "目标描述", "deadline": "YYYY-MM-DD"},
  "milestones": [{"title": "开题报告", "due_date": "YYYY-MM-DD"}],
  "goals": [
    {"level": "quarter", "title": "季度目标", "parent": "父目标标题或 annual",
     "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD",
     "tasks": [{"title": "具体任务", "due_date": "YYYY-MM-DD", "priority": 3}]}
  ]
}"""


def _extract_json(text: str) -> dict:
    """从 AI 输出中提取 JSON 对象（容忍 markdown 代码块/前后缀）。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _plan(mode: str, content: str, context: str = "") -> dict:
    system = (
        "你是研究生的科研规划助手，负责把用户的需求或文字拆解成可执行的科研规划。"
        "你只能输出一个 JSON 对象，不要输出任何解释、前后缀或 markdown 代码块标记。\n"
        f"JSON 结构必须如下：\n{_PLAN_SCHEMA}\n"
        "规则：\n"
        "- level 只能是 annual/quarter/month/week\n"
        "- parent 填写父目标的标题，第一层统一填 annual\n"
        "- 所有日期用 YYYY-MM-DD 字符串，无法确定时给出合理估算值\n"
        "- priority 为 1-5 的整数，数字越大越紧急重要\n"
        "- goals 至少包含季度/月度/周目标，层层分解，每层携带具体任务\n"
        "- milestones 是毕业关键节点（如开题/中期/答辩），都带 due_date\n"
    )
    if mode == "parse":
        user = f"请识别并整理以下规划文字（纯文字、无格式），填入对应层级后输出 JSON：\n{content}"
    elif mode == "optimize":
        user = (
            "用户当前已有以下数据。请基于这些数据补全、优化并生成更完整的规划"
            "（只做新增与建议，不要删除已有内容）：\n\n"
            f"{context or '（无额外数据）'}\n\n"
            f"用户补充说明：{content or '（无）'}"
        )
    else:
        user = f"请根据用户的一句话描述，生成一份完整科研规划并输出 JSON：\n{content}"
    if context and mode != "optimize":
        user += f"\n\n可参考的现有数据：\n{context}"

    for attempt in range(2):
        raw = chat([{"role": "user", "content": user}], system, temperature=0.3)
        try:
            return _extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            if attempt == 0:
                user += "\n\n注意：你上次的输出不是合法 JSON，请只输出合法 JSON 对象。"
            else:
                raise AIError("AI 返回的规划不是合法 JSON，请重试")


def generate_plan(description: str, context: str = "") -> dict:
    """根据一句话描述生成完整规划（JSON dict）。"""
    return _plan("generate", description, context)


def parse_plan(text: str, context: str = "") -> dict:
    """识别粘贴的纯文字规划，填入对应层级（JSON dict）。"""
    return _plan("parse", text, context)


def optimize_plan(context: str, note: str = "") -> dict:
    """基于现有数据优化/补全规划（JSON dict）。"""
    return _plan("optimize", note, context)


# ---------- 每日清单 / 文献推荐（返回 JSON 数组）----------
def _extract_json_value(text: str):
    """从 AI 输出提取 JSON（dict 或 list），容忍 markdown/前后缀。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    s = text.find("[")
    e = text.rfind("]")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s : e + 1])
        except Exception:
            pass
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s : e + 1])
        except Exception:
            pass
    raise ValueError("no json in output")


def _ai_json(system: str, user: str, temperature: float = 0.3):
    """调用 AI 并强制解析 JSON（dict/list），失败重试 1 次。"""
    for attempt in range(2):
        raw = chat([{"role": "user", "content": user}], system, temperature=temperature)
        try:
            return _extract_json_value(raw)
        except (ValueError, json.JSONDecodeError):
            if attempt == 0:
                user += "\n\n注意：你上次输出不是合法 JSON，请只输出合法 JSON。"
            else:
                raise AIError("AI 返回格式异常，请重试")


def generate_daily_plan(context: str) -> list[dict]:
    system = (
        "你是研究生的每日日程规划助手。根据用户的今日侧重方向、当前阶段目标、作战计划（当前阶段/本周目标/每日固定节奏）、任务、习惯、待读文献、技能进度、昨日未完成项与长期规划，"
        "生成今日清单建议（建议追加，不要重复已列出的项；与已有项是「同一件事」但换了说法/加了细节的，同样不要推荐）。"
        "推荐 5~7 条，并按你认为的优先级从高到低排序：最应该做、最能推进今日侧重方向与本周阶段目标的事项排最前面。"
        "硬性要求：所有任务必须服务于作战计划中「本周论文线/技术线目标」与当前阶段目标；计划里写了固定节奏的，把对应任务安排进匹配的时间段。"
        "宁缺毋滥：每条都必须具体、可执行、今天真能完成；不要罗列全部待读文献或技能，只挑与侧重方向/阶段目标/本周目标相关的。"
        "提到具体文献时，content 里写出论文标题（可附「文献N」编号），不要只写编号。"
        "只输出 JSON 数组，不要任何解释文字或 markdown 代码块。\n"
        '数组元素格式：{"content":"要做的事","kind":"task/habit/literature/manual","source_id":数字或null,'
        '"quadrant":"important_urgent/important_not/not_urgent_important/not_important_not",'
        '"pomodoros":预计番茄数(整数),"weight":1-100整数(代表这项占今天精力的比重),'
        '"time_range":"HH:MM-HH:MM 或空字符串（若作战计划有固定节奏，尽量落入对应时间段）",'
        '"due_date":"YYYY-MM-DD或空","reason":"推荐理由（说明它对应本周哪条目标/节奏）"}'
        "\n规则：习惯与关键任务优先放重要紧急；学习/技能类放重要不紧急；每条都要有具体可执行的内容。"
    )
    return _ai_json(system, context, temperature=0.3)


def generate_advisor_report(context: str) -> str:
    """按 05 模板生成给导师的周报草稿。"""
    system = (
        "你是研究生写给导师的周报助手。根据用户本周的真实产出数据（完成任务、科研/文献/实验进展、技能学习、刷题、时间投入）"
        "与作战计划目标，生成一封给导师的周报草稿。固定格式：\n"
        "导师您好，本周汇报：\n\n"
        "1. 本周进展：\n   - （技术/课题进度 1-2 条）\n   - 遇到的问题：\n"
        "2. 下周计划：\n   - （1-2 条，与作战计划的本周/下周目标一致）\n"
        "3. 需要您指导的地方：\n   - （1 条，结合课题/论文提出具体问题）\n\n"
        "要求：语气礼貌、简洁、突出与课题和论文相关的内容；只依据提供的数据，不编造成果；"
        "直接输出周报正文（纯文本，可用简单列表），不要任何解释或 markdown 代码块标记。"
    )
    return chat([{"role": "user", "content": context}], system, temperature=0.4)


def recommend_literature(context: str) -> list[dict]:
    system = (
        "你是科研文献推荐助手。根据待读文献列表（含年份/标签/摘要），推荐今天最值得读的 3-5 篇。"
        "优先：年份较新、与红外小目标检测高度相关、领域经典。只输出 JSON 数组，不要解释文字或 markdown。\n"
        '数组元素格式：{"id":文献数字id,"reason":"推荐理由（说明年份/相关度/为什么今天读）"}'
    )
    return _ai_json(system, context, temperature=0.2)


def daily_paper_guide(candidates: list[dict], context: str = "") -> dict:
    """从候选论文中挑选今天最值得读的一篇，并生成中文导读。

    返回 {"paper": 标题, "summary": 中文导读, "why_read": 为什么值得读, "relation": 与用户方向的关联}。
    """
    lines = []
    for i, c in enumerate(candidates):
        y = c.get("year") or "?"
        cites = c.get("citation_count")
        cite_str = f"{cites} 次引用" if cites else "引用未知/过新"
        lines.append(f"[{i}] {c.get('title')}（{y}）期刊/会议:{c.get('publication') or '未知'} 引用:{cite_str}")
    system = (
        "你是红外小目标检测（IRSTD）领域的文献推荐专家。下面是从学术数据库检索到的候选论文，"
        "请从中挑选一篇「今天最值得推荐给用户阅读」的论文。挑选标准按重要性排序：\n"
        "1. 新颖：优先近 1-2 年（2024 年及以后）的论文；经典里程碑论文（引用数极高）也可作为补充；\n"
        "2. 引用/评价高：领域内引用数高、期刊/会议等级高（TPAMI/TIP/TGRS/CVPR/ICCV 等）或领域公认重要；"
        "注意这是垂直领域，领域内高引即为高评价；\n"
        "3. 与用户当前研究方向与阶段目标契合；\n"
        "4. 只选红外小目标相关（检测/分割/跟踪/数据集/综述均可），排除明显无关论文。\n"
        "只输出一个 JSON 对象，不要输出任何解释或 markdown 代码块：\n"
        '{"paper":"选中论文的标题（必须与候选列表完全一致）",'
        '"summary":"中文导读，200字内，概述论文解决的问题、方法核心与亮点",'
        '"why_read":"为什么今天值得读（新颖性/引用评价/里程碑价值），80字内",'
        '"relation":"与用户研究方向/当前阶段目标的关联，80字内"}'
    )
    user = f"用户背景：\n{context or '（无）'}\n\n候选论文列表：\n" + "\n".join(lines)
    raw = _ai_json(system, user, temperature=0.3)
    if not isinstance(raw, dict):
        raise AIError("AI 返回格式异常，请重试")
    return raw


def analyze_drink_nutrition(name: str, volume_ml: int | None = None, research: str = "") -> dict:
    """分析饮品营养成分（联网检索资料 + 模型知识），返回标准化 dict。

    返回 {"volume_ml", "calories", "sugar_g", "fat_g", "confidence", "note"}。
    calories/sugar_g/fat_g 均为「整杯合计」估算值；现制奶茶等无权威数据时按行业常见值估算。
    """
    system = (
        "你是营养学助手，负责估算用户所喝饮品的营养成分（糖分/脂肪/热量）。"
        "只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块。\n"
        "JSON 结构：{\"volume_ml\":整数(毫升), \"calories\":数字(千卡,整杯合计), "
        "\"sugar_g\":数字(克,整杯合计), \"fat_g\":数字(克,整杯合计), "
        "\"confidence\":\"high/medium/low\", \"note\":\"30字以内的依据说明与不确定性\"}\n"
        "估算规则：\n"
        "- 包装饮料（可乐/瓶装茶/乳饮料等）按该产品的常见规格营养数据估算；\n"
        "- 现制饮品（奶茶/咖啡/果茶）按标准糖、标准杯的行业常见值估算，"
        "参考区间：全糖珍珠奶茶 500ml 约 400-520kcal、糖 40-55g、脂肪 8-15g；"
        "半糖约减去 1/3 糖；如能判断品牌（如蜜雪冰城/瑞幸/喜茶）优先用该品牌常见款数据；\n"
        "- 数值一律换算为整杯/整瓶合计（按给定容量或常见容量）；\n"
        "- confidence 反映你对本次估算的把握：有明确产品数据=high，常见品类=medium，模糊名称=low。"
    )
    user = f"饮品名称：{name}\n"
    if volume_ml:
        user += f"容量：约 {volume_ml} ml\n"
    if research:
        user += f"\n以下是联网检索到的参考资料（可能含噪声，请甄别使用）：\n{research[:2000]}\n"
    data = _ai_json(system, user, temperature=0.2)
    if not isinstance(data, dict):
        raise AIError("AI 返回格式异常，请重试")
    out: dict = {}
    try:
        out["volume_ml"] = max(0, min(3000, int(float(data.get("volume_ml") or volume_ml or 0))))
    except (TypeError, ValueError):
        out["volume_ml"] = int(volume_ml or 0)
    for key, cap in (("calories", 5000), ("sugar_g", 500), ("fat_g", 500)):
        try:
            out[key] = round(max(0.0, min(float(cap), float(data.get(key) or 0))), 1)
        except (TypeError, ValueError):
            out[key] = 0.0
    conf = str(data.get("confidence") or "medium").strip().lower()
    conf = {"高": "high", "中": "medium", "低": "low"}.get(conf, conf)
    out["confidence"] = conf if conf in ("high", "medium", "low") else "medium"
    out["note"] = str(data.get("note") or "").strip()[:80]
    return out


def estimate_task_times(tasks: list[dict]) -> dict:
    """AI 预估任务时长：入参 [{id,title,type,priority,due,goal}]，返回 {任务id: 预估分钟数}。

    按任务性质给出符合研究生科研实际的单次投入预估（习惯/学习类按每日一次计）。
    """
    lines = []
    for t in tasks:
        due = t.get("due") or "无"
        lines.append(f"- [{t['id']}] {t.get('title')}（类型 {t.get('type')}，优先级 {t.get('priority')}，DDL {due}）")
    system = (
        "你是科研任务时间估算助手。根据任务标题、类型、优先级与截止日期，估算完成该任务需要的单次投入分钟数。"
        "规则：按研究生实际节奏，宁保守勿激进；优先考虑 25 分钟番茄钟整倍数；一次性任务按总工作量估算，"
        "习惯/学习类任务按「每天一次」的投入估算；简单杂事 5-30 分钟，中等任务 30-120 分钟，"
        "复杂任务（复现论文/写综述章节/实验）可 120-480 分钟。只输出 JSON 对象，键为任务 id 数字，值为整数分钟。"
    )
    raw = _ai_json(system, "\n".join(lines), temperature=0.2)
    out: dict = {}
    if isinstance(raw, list):
        # 容错：AI 返回数组 [{id, minutes}]
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                tid = int(item.get("id"))
                mins = item.get("minutes") or item.get("est_minutes") or item.get("est")
                out[tid] = max(5, min(1440, int(mins)))
            except (ValueError, TypeError):
                continue
    elif isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[int(k)] = max(5, min(1440, int(v)))
            except (ValueError, TypeError):
                continue
    return out
