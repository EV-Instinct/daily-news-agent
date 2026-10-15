# -*- coding: utf-8 -*-
"""
每日新闻简报 Agent
=================
角色：你的私人新闻编辑
工具：GLM（归纳）+ RSS（采集）
记忆：问答上下文保存在内存中（_qa_history），进程重启即清空
自主：启动时自动检查并生成当日简报

用法：
    python agent.py              启动服务（浏览器打开 http://127.0.0.1:8848）
    python agent.py --run        只跑一次生成简报，不启服务（供定时任务调用）
    python agent.py --search 芯片 按关键词生成一次简报
    python agent.py --check      实测各RSS 源可用性
"""

import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
BRIEFING = DATA / "briefing.json"

load_dotenv(BASE / ".env")
# 兼容旧配置：优先读 ZHIPUAI_API_KEY，其次回落到旧的 DASHSCOPE_API_KEY
API_KEY = (os.getenv("ZHIPUAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
MODEL = os.getenv("AGENT_MODEL", "glm-4-flash").strip()
MODEL_QA = os.getenv("AGENT_MODEL_QA", "").strip() or MODEL
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "1200"))

# 智谱 GLM 的 OpenAI 兼容端点
GLM_BASE_URL = os.getenv(
    "AGENT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
).strip()


def get_client():
    """创建 OpenAI 兼容客户端（智谱 GLM）。延迟导入避免启动即依赖 openai 包。"""
    from openai import OpenAI

    return OpenAI(api_key=API_KEY, base_url=GLM_BASE_URL)

# ============================================================
# 角色定义 —— Agent 的人格与职责
# ============================================================
PERSONA = """你是严谨克制的私人新闻编辑。只做筛选归纳，绝不编造新闻、来源或数据。
语言平实，不用标题党措辞。"""

# ============================================================
# 工具：RSS 源（经2026-10-14 实测，24h 内均有更新）
# ============================================================
SOURCES = {
    "中新网-滚动": "https://www.chinanews.com.cn/rss/scroll-news.xml",
    "中新网-财经": "https://www.chinanews.com.cn/rss/finance.xml",
    "中新网-社会": "https://www.chinanews.com.cn/rss/society.xml",
    "中新网-国际": "https://www.chinanews.com.cn/rss/world.xml",
    "华尔街见闻":  "https://dedicated.wallstreetcn.com/rss.xml",
    "IT之家":     "https://www.ithome.com/rss/",
    "钛媒体":      "https://www.tmtpost.com/feed",
    "少数派":      "https://sspai.com/feed",
    "cnBeta":     "https://www.cnbeta.com.tw/backend.php",
    "开源中国":     "https://www.oschina.net/news/rss",
    "Solidot":    "https://www.solidot.org/index.rss",
}

CATEGORIES = {
    "时政": ["中新网-滚动", "中新网-社会"],
    "财经": ["中新网-财经", "华尔街见闻"],
    "国际": ["中新网-国际"],
    "科技": ["IT之家", "钛媒体", "cnBeta", "开源中国", "Solidot"],
    "生活": ["少数派"],
}

# ============================================================
# 同义词扩展：用户搜"直升机"，新闻里可能写"UH-60"/"武装直升机"
# 纯字符串匹配会漏，这里用轻量映射表补足（不依赖模型，零延迟）
# ============================================================
SYNONYMS = {
    "直升机": ["直升机", "UH-60", "直-20", "武装直升机", "航空"],
    "芯片": ["芯片", "半导体", "晶圆", "光刻", "存储芯片", "算力", "英伟达", "台积电", "asml"],
    "半导体": ["半导体", "芯片", "晶圆", "光刻", "封装"],
    "ai": ["ai", "人工智能", "大模型", "llm", "gpt", "机器学习", "openai", "深度学习"],
    "人工智能": ["人工智能", "ai", "大模型", "llm", "openai"],
    "大模型": ["大模型", "llm", "ai", "人工智能", "claude", "gpt"],
    "股市": ["股市", "a股", "上证", "深证", "创业板", "指数", "券商", "成交"],
    "股票": ["股票", "a股", "股市", "上证", "指数"],
    "a股": ["a股", "上证", "深证", "创业板", "指数", "股市"],
    "金融": ["金融", "银行", "证券", "保险", "央行", "货币", "信贷"],
    "经济": ["经济", "gdp", "通胀", "cpi", "就业", "消费", "增长"],
    "汽车": ["汽车", "新能源车", "电动车", "车企", "比亚迪", "特斯拉", "吉利", "长城"],
    "新能源汽车": ["新能源汽车", "电动车", "汽车", "锂电", "充电桩", "车企"],
    "电池": ["电池", "锂电", "储能", "宁德时代", "固态电池", "充电"],
    "手机": ["手机", "iphone", "安卓", "鸿蒙", "出货量", "小米", "华为", "苹果"],
    "房地产": ["房地产", "楼市", "房价", "地产", "房企", "住房"],
    "spacex": ["spacex", "星舰", "星链", "马斯克", "火箭"],
    "马斯克": ["马斯克", "spacex", "特斯拉", "星舰"],
    "航天": ["航天", "火箭", "卫星", "spacex", "发射", "星舰"],
    "军工": ["军工", "国防", "导弹", "战机", "海军", "空军"],
    "能源": ["能源", "电力", "煤炭", "石油", "天然气", "新能源"],
    "光伏": ["光伏", "硅料", "组件", "太阳能", "硅片"],
    "医药": ["医药", "药品", "疫苗", "医保", "医院", "生物医药"],
    "教育": ["教育", "高考", "学校", "学生", "教师", "校园"],
    "战争": ["战争", "冲突", "袭击", "军事", "停火", "乌克兰", "以色列"],
    "国际": ["国际", "海外", "全球", "联合国", "外交", "使馆"],
    "茅台": ["茅台", "白酒", "贵州茅台", "酒企"],
    "白酒": ["白酒", "茅台", "五粮液", "酒企"],
    "小米": ["小米", "雷军", "redmi", "米家"],
    "华为": ["华为", "鸿蒙", "麒麟", "昇腾", "任正非"],
    "特斯拉": ["特斯拉", "马斯克", "上海工厂", "降价"],
    "谷歌": ["谷歌", "google", "gemini", "alphabet"],
    "苹果": ["苹果", "iphone", "ipad", "macbook", "库克"],
    "英伟达": ["英伟达", "nvidia", "黄仁勋", "黑 Blackwell", "cuda"],
}


def expand_keywords(kw: str) -> list[str]:
    """把用户输入扩展成多个匹配词（原词 + 同义词）。"""
    base = [k.strip() for k in re.split(r"[\s,，、;；/]+", kw) if k.strip()]
    extra = []
    for b in base:
        extra.extend(SYNONYMS.get(b.lower(), []))
    # 原词优先，同义词去重
    return list(dict.fromkeys(base + extra))


# ============================================================
# 检索词生成：让模型输出「原子词」而非组词
# 实测：模型直接输出「芯片行业最新动态」会匹配不到任何新闻，
#      要求它输出「芯片」「半导体」等单个实体词后命中率大幅提升
# ============================================================
KEYWORD_SYS = """你是新闻检索助手。为用户问题生成检索词，用于在今日新闻库中匹配。

硬性规则：
1. 每个词必须是**单个实体、品牌、领域或术语**，长度 2-8 字
   ✓ 好：芯片、半导体、宁德时代、A股、特斯拉
   ✗ 差：芯片行业最新动态、宁德时代财务报告、今日新闻
2. 生成 5-7 个词，覆盖：
   - 用户提到的实体原名
   - 所在行业/领域
   - 上下游或相关概念
3. 禁止输出"最新消息""今日动态""相关报道"这类无检索价值的词
4. 只输出 JSON 字符串数组，不要任何解释"""

STOPWORDS = {"最新消息", "最新动态", "新消息", "今天", "今日", "新闻", "消息",
             "动态", "报道", "最新", "相关", "资讯", "情况", "怎么样",
             "是什么", "有什么", "怎么回事", "如何", "哪些"}

# 通用词：单独出现不足以判定相关，必须配合实体词
GENERIC = {"研究", "成果", "进展", "消息", "报道", "情况", "分析", "发展",
           "工作", "推出", "举行", "发布", "召开", "我国", "中国", "国家",
           "实现", "获得", "完成", "正式", "最新", "今日", "相关", "有关",
           "重大", "重要", "关注", "目前", "近日", "日前"}


def atomize(phrases: list) -> list:
    """清洗模型的检索词：去停用词、过长项拆分、去重。"""
    out = []
    for p in phrases:
        if not isinstance(p, str):
            continue
        # 拆空格/逗号
        parts = re.split(r"[\s,，、;；/]+", p)
        for w in parts:
            w = w.strip()
            if not w or w in STOPWORDS:
                continue
            # 过长的词（如"芯片行业最新动态"）尝试按已知词根切
            if len(w) > 8:
                matched = False
                for root in SYNONYMS:
                    if root in w and len(root) >= 2:
                        out.append(root)
                        matched = True
                if matched:
                    continue
                out.append(w[:8])
            elif len(w) >= 2:
                out.append(w)
    return list(dict.fromkeys(out))


# 疑问词/无检索价值的成分
_QWORDS = {"最近", "今日", "今天", "怎么样", "怎么", "如何", "什么", "为何",
           "为什么", "哪些", "是否", "关于", "消息", "新闻", "动态", "报道",
           "情况", "分析", "介绍", "说说", "讲讲", "有没有"}


def extract_terms(text: str, pool: list = None) -> list:
    """从自由文本抽取检索实体：优先用池中标题做子串对齐（最准），退化时用分词。"""
    out = []

    # 1) 从池中标题里找出出现在问题中的完整实体/术语（最可靠）
    if pool:
        blob = text
        cands = []
        for n in pool:
            t = n["title"]
            # 取标题中的中文片段（长度 2-6）作为候选实体
            for seg in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,6}", t):
                if seg in blob and seg not in cands:
                    cands.append(seg)
        # 长的候选优先（更可能是完整实体）
        out.extend(sorted(cands, key=len, reverse=True)[:8])

    # 2) jieba 分词兜底
    if len(out) < 3:
        try:
            import jieba
            words = [w.strip() for w in jieba.cut(text) if w.strip()]
        except Exception:
            words = re.split(r"[\s,，、;；/]+", text)

        buf = ""
        for w in words:
            if w in _QWORDS or len(w) < 2:
                continue
            if out and w == out[0][:len(w)]:      # 与首词重叠，跳过
                continue
            # 尝试与上一个拼成更长的实体
            if buf and len(buf + w) <= 8:
                merged = buf + w
                if pool and any(merged in n["title"] for n in pool):
                    out.insert(0, merged)
                    buf = ""
                    continue
            buf = w
            if len(out) < 8 and w not in out:
                out.append(w)

    return [w for w in dict.fromkeys(out) if w not in _QWORDS][:10]


def relevance(news: dict, terms: list) -> float:
    """打分：实体词命中标题权重高，同义词命中摘要权重低。"""
    title = news["title"].lower()
    summ = (news["summary"] or "").lower()
    score = 0.0
    for t in terms:
        tl = t.lower()
        if tl in title:
            score += 3.0
        if tl in summ:
            score += 1.0
    return score


def clean_keywords(kws: list) -> list:
    """清洗模型给的检索词：剔除疑问句式残留，抽出纯实体。"""
    out = []
    for k in kws or []:
        if not isinstance(k, str):
            continue
        k = k.strip()
        # 明显是整句疑问的，抽出其中的实体
        if len(k) > 6 or any(w in k for w in
                             ("怎么", "如何", "什么", "为什么", "吗", "？", "?", "哪")):
            parts = extract_terms(k)
            out.extend(parts if parts else [k])
        elif len(k) >= 2:
            out.append(k)
    # 去重但保留顺序
    seen, res = set(), []
    for w in out:
        if w not in seen and w not in _QWORDS:
            seen.add(w)
            res.append(w)
    return res[:8] or (kws or [])[:5]


def smart_search(phrases: list, pool: list, top: int = 18) -> list:
    """智能检索：原子化 → 同义词扩展 → 相关性排序 → 命中不足时适度放宽。

    关键约束：通用词（研究/成果/进展…）单独出现不算命中，
    必须至少命中一个"实体词"才算真正相关，避免问物理学匹配到
    "中美元首会晤成果"这类假匹配。
    """
    terms = atomize(phrases)
    for t in terms[:8]:                      # 只扩展前 8 个原子词，避免词表膨胀
        terms.extend(SYNONYMS.get(t.lower(), []))
    terms = list(dict.fromkeys([x.lower() for x in terms]))[:40]

    # 区分实体词与通用词
    generic = [t for t in terms if t in GENERIC]
    entity = [t for t in terms if t not in GENERIC]

    scored = []
    for n in pool:
        s = relevance(n, terms)
        if s <= 0:
            continue
        # 只有通用词命中、实体词一个没中 → 判为假匹配
        if entity and not any(e in (n["title"] + n["summary"]).lower()
                              for e in entity):
            continue
        # 连通用词都没有 → 显然不相关
        if not entity and not any(g in n["title"].lower() for g in generic):
            continue
        scored.append((s, n))
    if not scored:
        return []

    # 主体词（模型给的前 3 个）权重更高，用于拉开差距
    core = [t.lower() for t in (entity or terms)[:3]]
    rescored = []
    for s, n in scored:
        bonus = sum(2.0 for c in core if c in n["title"].lower())
        rescored.append((s + bonus, n))

    rescored.sort(key=lambda x: -x[0])

    # 命中不足 3 条时适度放宽：仅用实体词在摘要中找，不用通用词
    if len(rescored) < 3 and entity:
        seen = {id(n) for _, n in rescored}
        extra = []
        for n in pool:
            if id(n) in seen:
                continue
            blob = (n["title"] + n["summary"]).lower()
            if any(e in blob for e in entity):
                extra.append(n)
                seen.add(id(n))
            if len(extra) >= max(0, 3 - len(rescored)):
                break
        rescored.extend((1.0, n) for n in extra)

    # 最终只保留达到分数门槛的，避免塞入噪音
    MIN_SCORE = 2.0
    final = [(s, n) for s, n in rescored if s >= MIN_SCORE] or rescored[:1]
    return [n for _, n in final[:top]]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FRESH_HOURS = 30          # 新闻新鲜度窗口
PER_SOURCE_LIMIT = 12     # 每源最多取几条

# 回答时的时效硬约束：超过此时长的新闻一律不用于作答
ANSWER_MAX_AGE_H = 30


def cutoff() -> datetime:
    """动态计算时效线，避免长驻进程用模块加载时的旧值。"""
    return datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)

app = Flask(__name__)
_running = False
_lock = threading.Lock()
_news_pool = []          # 本次采集的原始新闻池，供搜索复用（避免重复抓取）
_last_health = []       # 上次采集的源健康状态，搜索时复用以便展示失效源

# ============================================================
# 任务状态机 —— 前端唯一可信的进度来源
# 不从 briefing.json 内容反推，避免"失败时永远等不到"的问题
# ============================================================
_state = {
    "running": False,
    "stage": "idle",      # idle | collecting | llm | done | error
    "keyword": None,      # 本次任务对应的关键词（全量时为 ""）
    "matched": 0,
    "elapsed": 0.0,
    "error": None,
    "dead_sources": [],   # 本次失效的数据源
    "started_at": None,
}


def set_stage(stage: str, **kw) -> None:
    _state["stage"] = stage
    _state.update(kw)
    print(f"[stage] {stage} {kw if kw else ''}")


# ============================================================
# 工具：RSS 采集
# ============================================================
def entry_time(e) -> datetime | None:
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        if k in e:
            try:
                return datetime(*e[k][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    t = e.get("published") or e.get("updated") or e.get("dc:date")
    if t:
        try:
            return parsedate_to_datetime(t).astimezone(timezone.utc)
        except Exception:
            return None
    return None


def clean(text: str) -> str:
    """去 HTML 标签、压缩空白。"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_one(name: str, url: str) -> tuple:
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.encoding = r.apparent_encoding or "utf-8"
        d = feedparser.parse(r.text)
        items = []
        for e in d.entries[:PER_SOURCE_LIMIT]:
            t = entry_time(e)
            if not t or t < cutoff():
                continue
            title = clean(e.get("title", ""))
            if not title:
                continue
            items.append({
                "title": title,
                "link": e.get("link", ""),
                "summary": clean(e.get("summary", ""))[:120],
                "source": name,
                "_ts": t.timestamp(),          # 供回答时做时效校验
                "time": t.astimezone(timezone(timedelta(hours=8))).strftime("%m-%d %H:%M"),
            })
        return name, items, None
    except Exception as ex:
        return name, [], f"{type(ex).__name__}"


def collect() -> tuple:
    """并发抓取所有源，返回 (新闻列表, 源健康状态)。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(lambda kv: fetch_one(*kv), SOURCES.items()))

    seen, news = set(), []
    health = []
    for name, items, err in results:
        if err:
            health.append({"name": name, "ok": False, "count": 0, "error": err})
            continue
        health.append({"name": name, "ok": bool(items), "count": len(items)})
        for it in items:
            key = it["title"][:24]
            if key in seen:
                continue
            seen.add(key)
            news.append(it)

    for it in news:
        it["category"] = next(
            (c for c, srcs in CATEGORIES.items() if it["source"] in srcs), "其他"
        )
    return news, health


# ============================================================
# 大模型：GLM 归纳
# ============================================================
def call_qwen(prompt: str, system: str = "") -> str:
    client = get_client()
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=msgs,
        temperature=0.2,
        max_tokens=MAX_TOKENS,
    )
    return resp.choices[0].message.content or ""


BRIEF_PROMPT = """下面是今天的新闻条目。请生成每日简报，严格输出 JSON，不要任何额外文字。

格式：
{{"highlights":[{{"title":"标题","digest":"一句话","source":"来源"}}],
 "sections":[{{"category":"分类名","items":[{{"title":"标题","digest":"一句话","source":"来源"}}]}}]}}

硬性要求：
1. highlights选 2 条最重要的，digest 说清"发生了什么+为什么重要"，**不超过 30 字**
2. sections 按需给出，每类最多 3 条，每条 digest **不超过 25 字**
3. 只输出你确实从条目中读到的内容，**绝不编造**
4. 分类名最多 4 个，用中文（如"科技""财经""时政""国际"）

条目列表：
{items}"""


def summarize(news: list) -> dict:
    if not API_KEY:
        raise RuntimeError("未配置 ZHIPUAI_API_KEY，请复制 .env.example 为 .env 并填入 Key")

    lines = []
    for i, n in enumerate(news, 1):
        lines.append(f"{i}. {n['title']}")
        if n["summary"]:
            lines.append(f"   {n['summary'][:60]}")

    raw = call_qwen(BRIEF_PROMPT.format(items="\n".join(lines)), system=PERSONA)
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    data = json.loads(clean)

    # Qwen 会改写标题，故用字符重叠度做模糊匹配回填链接
    pool = [(n["title"], n["link"]) for n in news if n["link"]]

    def sim(a: str, b: str) -> float:
        strip = lambda s: re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
        A, B = set(strip(a)), set(strip(b))
        return len(A & B) / min(len(A), len(B)) if A and B else 0.0

    def find_link(title: str) -> str:
        t = re.sub(r"\s+", "", title or "")
        best, score = "", 0.0
        for ot, ol in pool:
            s = sim(t, ot)
            if s > score:
                best, score = ol, s
        return best if score >= 0.5 else ""

    filled = 0
    for sec in data.get("sections", []):
        for it in sec.get("items", []):
            hit = find_link(it.get("title", ""))
            if hit:
                it["link"] = hit
                filled += 1
            else:
                it["link"] = ""
    for it in data.get("highlights", []):
        it["link"] = find_link(it.get("title", ""))

    total = sum(len(s.get("items", [])) for s in data.get("sections", []))
    if total:
        print(f"[link] 回填 {filled}/{total} 条原文链接")
    return data


# ============================================================
# 问答：两阶段模型调用
# 阶段1 模型自主决定检索词 → 阶段2 基于检索结果回答
# ============================================================
SEARCH_TOOL = [{
    "type": "function",
    "function": {
        "name": "search_news",
        "description": "检索今日新闻库。当用户询问时事、财经、科技、国际、公司、行业等话题时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "检索词。必须是单个实体/品牌/领域（2-8字），"
                                   "如['芯片','半导体','英伟达']。"
                                   "禁止输出'最新消息'这类无检索价值的词。",
                }
            },
            "required": ["keywords"],
        },
    }
}]

ASK_SYS = """你是一个新闻助手，回答用户关于**今日新闻**的问题。

工作方式：
1. 先调用 search_news 检索今日新闻库
2. 基于检索到的新闻回答用户问题

严格要求：
- 只使用检索结果中的内容作答，绝不编造任何新闻、数据、来源或时间
- 检索不到时，明确说"今日新闻库中没有 X 的报道"，绝对不要用训练知识里的旧闻代替
- **时间说明**：检索结果里的时间格式是"M-DD HH:MM"（如"10-14 16:20"），代表**今年今年今天所在的那个月日**，不是往年。回答时直接引用这个时间，不要自行推算或改写年份
- 每条结论必须能对应到检索结果中的具体某条，并标注来源与时间，如"（华尔街见闻 10-14）"
- 回答不少于 150 字；信息有限时如实说明，不要注水
- 用中文回答，简洁直接，先给结论再给依据"""


def _fresh_enough(news: list) -> list:
    """时效硬约束：只保留 ANSWER_MAX_AGE_H 小时内的新闻。"""
    now = datetime.now(timezone.utc).timestamp()
    return [n for n in news if n.get("_ts", 0) >= now - ANSWER_MAX_AGE_H * 3600]


def answer(question: str, history: list = None) -> dict:
    """回答一个问题。返回 {answer, keywords, refs, count}"""
    global _news_pool, _last_health
    if not API_KEY:
        raise RuntimeError("未配置 API Key")

    # 池为空时先采集，保证问答始终可用
    if not _news_pool:
        set_stage("collecting", running=True, keyword=None, started_at=time.time())
        news0, health0 = collect()
        if len(news0) < 5:
            raise RuntimeError("新闻库为空且采集失败，请检查网络或数据源")
        _news_pool = news0
        _last_health = health0

    client = get_client()

    # 阶段1：模型自己决定检索什么
    msgs = [{"role": "system", "content": ASK_SYS}]
    for h in (history or [])[-6:]:              # 带最近几轮上下文，支持追问
        msgs.append(h)
    msgs.append({"role": "user", "content": question})

    r1 = client.chat.completions.create(
        model=MODEL_QA, messages=msgs, tools=SEARCH_TOOL, tool_choice="auto",
        temperature=0.3, max_tokens=400)

    m1 = r1.choices[0].message
    keywords = []
    if m1.tool_calls:
        try:
            args = json.loads(m1.tool_calls[0].function.arguments)
            keywords = args.get("keywords") or []
        except Exception:
            pass
    if not keywords:
        # 模型没调工具：兜底直接用原问题里的词
        keywords = extract_terms(question, _news_pool)

    keywords = clean_keywords(keywords)

    # 检索 + 时效过滤
    hits = smart_search(keywords, _news_pool, top=18)

    # 保险：命中太少时用问题原文补充实体（不通配，避免污染）
    if len(hits) < 3:
        extra_terms = extract_terms(question, _news_pool)
        if extra_terms:
            merged = smart_search(list(dict.fromkeys(keywords + extra_terms)),
                                  _news_pool, top=18)
            if len(merged) > len(hits):
                hits = merged
                keywords = list(dict.fromkeys(keywords + extra_terms))

    hits = _fresh_enough(hits)

    # 语义校验：命中数少时，确认条目真的在讲核心实体
    # （避免"宁德时代"匹配到"吉利汽车"这种噪音）
    core_entity = [k for k in keywords if k.lower() not in GENERIC][:2]
    if hits and core_entity and len(hits) <= 2:
        strong = []
        for n in hits:
            blob = (n["title"] + " " + n["summary"]).lower()
            # 核心实体必须出现（标题优先，其次摘要）
            if any(e in n["title"].lower() for e in core_entity) or \
               sum(blob.count(e) for e in core_entity) >= 2:
                strong.append(n)
        if strong:
            hits = strong

    # ---- 分级：决定走新闻路还是知识路 ----
    if len(hits) >= 3:
        mode, source_type = "news", "news"          # 新闻充足
    elif len(hits) >= 1:
        mode, source_type = "news_thin", "news_thin"  # 少量新闻，照实说明
    else:
        mode, source_type = "knowledge", "knowledge"  # 完全没有→用模型知识

    # ---- 构造上下文 ----
    today = datetime.now().strftime("%Y年%m月%d日")
    if mode == "knowledge":
        ctx = ""
        instruction = (
            f"【重要】今日新闻库中没有任何与该问题相关的内容。\n"
            f"这说明你的问题不属于今日新闻范畴（可能是知识问答、学科概念、"
            f"历史、生活常识、技术方法等）。\n\n"
            f"请**直接用你自己的知识**回答这个问题，回答开头必须先说明："
            f"「以下为通用知识回答，非今日新闻」。\n"
            f"要求：内容准确、有条理，不少于 150 字；"
            f"如果是时效性强的信息（如最新版本、最新数据），"
            f"请注明你的知识可能存在滞后。")
    else:
        note = ("以下是今日新闻的相关报道，请优先基于这些内容回答"
                if mode == "news" else
                "今日新闻中仅有少量相关内容，请基于这些内容回答，"
                "并明确说明今日新闻中该方面的报道有限")
        ctx = (f"以下是【{today} 当天】的新闻检索结果：\n\n" +
               "\n".join(
                   f"[{i}] {n['time']}｜来源：{n['source']}｜标题：{n['title']}\n"
                   f"     摘要：{n['summary']}"
                   for i, n in enumerate(hits, 1)) +
               f"\n\n注意：以上全部是 {today} 的新闻。")
        instruction = f"{note}。每条结论标注来源与时间，如（华尔街见闻 10-14）。"

    msgs.append({"role": "assistant", "content": m1.content or "I'll search."})
    if m1.tool_calls:
        msgs.append({"role": "assistant", "tool_calls": m1.tool_calls,
                     "content": m1.content or ""})
    else:
        msgs.append({"role": "assistant",
                     "content": f"（拟检索关键词：{', '.join(keywords[:8])}）"})
    msgs.append({"role": "user", "content": f"{instruction}\n\n{ctx}"})

    r2 = client.chat.completions.create(
        model=MODEL_QA, messages=msgs, temperature=0.3, max_tokens=1200)
    text = r2.choices[0].message.content or ""

    # 组装可点击的原文链接
    refs = []
    for i, n in enumerate(hits, 1):
        if n["link"]:
            refs.append({
                "idx": i, "title": n["title"][:40], "source": n["source"],
                "time": n["time"], "link": n["link"],
            })

    print(f"[ask] '{question[:20]}' 词={keywords[:4]} 命中={len(hits)} 路={mode}")
    return {
        "question": question,
        "answer": text,
        "keywords": keywords[:8],
        "refs": refs[:10],
        "count": len(hits),
        "source_type": source_type,     # news | news_thin | knowledge
    }


# ============================================================
# 主流程
# ============================================================
def build_payload(news: list, health: list, keyword: str = "") -> dict:
    """把新闻交给模型生成简报，组装成前端要的 payload。"""
    t0 = time.time()
    brief = summarize(news)

    sections = brief.get("sections", [])
    # 搜索模式下按分类归并同名列，避免出现多个「xx」相关
    if keyword:
        merged, order = {}, []
        for s in sections:
            for it in s.get("items", []):
                if it.get("title") not in {x["title"] for x in merged.setdefault(s["category"], [])}:
                    merged[s["category"]].append(it)
                if s["category"] not in order:
                    order.append(s["category"])
        sections = [{"category": c, "items": merged[c]} for c in order if merged[c]]

    return {
        "date": datetime.now().strftime("%Y年%m月%d日"),
        "weekday": "周" + "一二三四五六日"[datetime.now().weekday()],
        "generated_at": datetime.now().strftime("%H:%M"),
        "keyword": keyword,
        "highlights": brief.get("highlights", []),
        "sections": sections,
        "stats": {
            "collected": len(news),
            "sources_ok": sum(1 for h in health if h["ok"]),
            "sources_total": len(health),
            "elapsed": round(time.time() - t0, 1),
            "matched": len(news) if keyword else 0,
            "pool": len(_news_pool),
        },
    }


def generate(keyword: str = "") -> dict:
    global _running, _news_pool, _last_health
    if not _lock.acquire(blocking=False):
        return {"ok": False, "msg": "正在生成中，请稍候"}
    _running = True
    t0 = time.time()
    set_stage("collecting" if not keyword else "matching",
              running=True, keyword=keyword, error=None, started_at=t0)
    try:
        if keyword and _news_pool:
            news, health = _news_pool, _last_health
        else:
            set_stage("collecting", running=True, keyword=keyword, started_at=t0)
            # 首次搜索且池为空时，需要先抓取全量再筛选，多花几秒
            news, health = collect()
            if len(news) < 5:
                raise RuntimeError(
                    f"只采集到 {len(news)} 条新闻，所有数据源可能都已失效。"
                    "这通常是源地址变更所致，请检查 agent.py 中的 SOURCES 配置。")
            _news_pool = news
            _last_health = health
            if keyword:
                set_stage("matching", running=True, keyword=keyword, started_at=t0)

        if keyword:
            kws = [k.lower() for k in expand_keywords(keyword)]
            hit = []
            for n in news:
                blob = (n["title"] + " " + n["summary"]).lower()
                if any(k in blob for k in kws):
                    hit.append(n)
            if not hit:
                return _fail(f"今日新闻里没有「{keyword}」相关内容",
                             keyword=keyword, elapsed=round(time.time() - t0, 1))
            news = hit

        set_stage("llm", running=True, keyword=keyword, matched=len(news),
                  started_at=t0)
        payload = build_payload(news, health, keyword)

        # 记录失效源，供前端提示
        dead = [h["name"] for h in health if not h.get("ok")]
        set_stage("writing", running=True, keyword=keyword, matched=len(news))
        payload["stats"]["dead_sources"] = dead
        BRIEFING.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")

        el = round(time.time() - t0, 1)
        set_stage("done", running=False, keyword=keyword, matched=len(news),
                  elapsed=el, error=None, dead_sources=dead)
        print(f"[gen] {'搜索' if keyword else '全量'} {len(news)} 条 / {el}s")
        return {"ok": True, "msg": "生成成功", "count": len(news), "elapsed": el}
    except Exception as ex:
        traceback.print_exc()
        return _fail(str(ex), keyword=keyword, elapsed=round(time.time() - t0, 1))
    finally:
        _running = False
        _lock.release()


def _fail(msg: str, **kw) -> dict:
    """失败也要落状态，前端才能立刻停止等待。"""
    kw.setdefault("keyword", None)
    kw.setdefault("elapsed", 0)
    kw.setdefault("matched", 0)
    set_stage("error", running=False, error=msg, **kw)
    print(f"[fail] {msg}")
    return {"ok": False, "msg": msg, **kw}


# ============================================================
# Web
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/briefing")
def api_briefing():
    if BRIEFING.exists():
        return jsonify(json.loads(BRIEFING.read_text(encoding="utf-8")))
    return jsonify({"error": "no_data", "msg": "尚未生成简报"}), 404


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    if _running:
        return jsonify({"ok": False, "msg": "正在生成中"})
    threading.Thread(target=generate, daemon=True).start()
    return jsonify({"ok": True, "msg": "开始生成"})


@app.route("/api/search", methods=["POST"])
def api_search():
    """同步执行并返回结果，便于前端立即渲染。"""
    kw = (request.json or {}).get("keyword", "").strip()
    if not kw:
        return jsonify({"ok": False, "msg": "请输入关键词"})
    if _running:
        return jsonify({"ok": False, "msg": "正在生成中，请稍候再试"})
    r = generate(kw)
    return jsonify(r)


_qa_history = []          # 最近问答，用于理解追问


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """问答接口。同步返回，通常 2-5 秒。"""
    global _qa_history
    q = ((request.json or {}).get("question") or "").strip()
    if not q:
        return jsonify({"ok": False, "msg": "请输入问题"}), 400
    if _running:
        return jsonify({"ok": False, "msg": "早报正在生成，请稍后再问"}), 409
    try:
        t0 = time.time()
        r = answer(q, _qa_history[-4:])
        _qa_history.append({"role": "user", "content": q})
        _qa_history.append({"role": "assistant", "content": r["answer"][:600]})
        _qa_history = _qa_history[-8:]
        r["elapsed"] = round(time.time() - t0, 1)
        r["ok"] = True
        return jsonify(r)
    except Exception as ex:
        traceback.print_exc()
        return jsonify({"ok": False, "msg": str(ex)}), 500


@app.route("/api/ask_clear", methods=["POST"])
def api_ask_clear():
    """清空对话上下文。"""
    global _qa_history
    _qa_history = []
    return jsonify({"ok": True, "msg": "已清空上下文"})


@app.route("/api/status")
def api_status():
    """任务状态查询——前端靠它判断该显示什么，而不是从数据内容猜。"""
    el = 0.0
    if _state["started_at"]:
        el = round((_state.get("elapsed") or
                    time.time() - _state["started_at"]), 1)
    return jsonify({
        "running": bool(_running),
        "stage": _state["stage"],
        "keyword": _state["keyword"],
        "matched": _state["matched"],
        "elapsed": el,
        "error": _state["error"],
        "dead_sources": _state.get("dead_sources", []),
        "pool": len(_news_pool),
    })


@app.route("/api/search_async", methods=["POST"])
def api_search_async():
    """立即返回，后台生成，前端轮询 /api/status。"""
    kw = (request.json or {}).get("keyword", "").strip()
    if not kw:
        return jsonify({"ok": False, "msg": "请输入关键词"})
    if _running:
        return jsonify({"ok": False, "msg": "正在生成中，请稍候再试"})
    threading.Thread(target=generate, args=(kw,), daemon=True).start()
    return jsonify({"ok": True, "keyword": kw})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """清除搜索，回到全量简报。"""
    if _running:
        return jsonify({"ok": False, "msg": "正在生成中，请稍候"})
    threading.Thread(target=generate, daemon=True).start()
    return jsonify({"ok": True, "msg": "已恢复全量简报"})


def auto_generate_if_stale():
    """启动时若今日数据缺失、或停留在筛选态、或新闻池为空，则后台跑一次全量。"""
    need = True
    if BRIEFING.exists() and _news_pool:
        try:
            d = json.loads(BRIEFING.read_text(encoding="utf-8"))
            today = datetime.now().strftime("%Y年%m月%d日")
            # 当天已有完整全量简报才跳过；带 keyword 说明是筛选残留，需重置
            if d.get("date") == today and not d.get("keyword"):
                need = False
        except Exception:
            pass
    if need:
        # 池空时也走这里，确保问答功能可用
        threading.Thread(target=generate, daemon=True).start()
    else:
        set_stage("done", running=False, keyword="")


if __name__ == "__main__":
    if "--check" in sys.argv:
        n, h = collect()
        print(f"采集 {len(n)} 条\n")
        for x in h:
            print(f"{'OK ' if x['ok'] else 'ERR'} {x['name']:12} {x['count']:3}条 {x.get('error','')}")
        sys.exit(0)

    if "--run" in sys.argv:
        r = generate()
        print(r["msg"])
        sys.exit(0 if r["ok"] else 1)

    if "--search" in sys.argv:
        kw = sys.argv[sys.argv.index("--search") + 1]
        r = generate(kw)
        print(r["msg"])
        sys.exit(0 if r["ok"] else 1)

    auto_generate_if_stale()
    print("\n  每日新闻简报 Agent 已启动")
    print("  → http://127.0.0.1:8848\n")
    app.run(host="127.0.0.1", port=8848, debug=False)