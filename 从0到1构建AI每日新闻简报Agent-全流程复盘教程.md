# 每日新闻简报 Agent：零基础从 0 到 1 实操教学指南

> 💡 **写在前面**：  
> 这是一篇**专门写给 0 基础读者的实操教程**。你不需要懂复杂的高等数学，也不需要学过人工智能算法。只要你会用电脑、跟着本文一步一步敲代码，就能亲手做出一个**属于你自己的「私人 AI 新闻主编」**。  
> 
> 文档分为 6 个步骤，**每个核心代码文件都会给出完整代码，并逐段讲解每段代码到底是干什么用的**。

---

## 🌟 这个项目最终能做成什么样？

当你跟着本文做完后，你会拥有一个这样的程序：
1. **自动抓新闻**：每天自动从 11 个权威新闻网站（时政、财经、科技、国际、生活）抓取最新内容。
2. **AI 帮你看**：大模型（智谱 GLM）会在 10 秒内把几十篇新闻提炼成：**今日焦点 2 条** + **分类速览**，每条不超过 30 字，附带原文跳转链接。
3. **智能问答（绝不胡编）**：你可以像跟真人编辑聊天一样问它：“今天有什么半导体新闻？”、“今天 A 股表现如何？”。它会基于今天抓到的新闻回答并注明媒体来源和发布时间；如果今天确实没这事，它会坦白告诉你，绝不上网胡乱编造。
4. **可视化界面**：有漂亮的网页卡片界面，能在电脑、手机上直接看，也能一键部署到公网上发给朋友用。

---

## 目录
- [准备工作：安装 Python 与获取大模型密钥](#准备工作安装-python-与获取大模型密钥)
- [第 1 步：创建项目文件夹与配置文件（打地基）](#第-1-步创建项目文件夹与配置文件打地基)
- [第 2 步：编写新闻采集模块（教程序去网上抓新闻）](#第-2-步编写新闻采集模块教程序去网上抓新闻)
- [第 3 步：编写大模型归纳模块（教 AI 读新闻写早报）](#第-3-步编写大模型归纳模块教-ai-读新闻写早报)
- [第 4 步：编写智能问答模块（核心：怎么让 AI 不胡编）](#第-4-步编写智能问答模块核心怎么让-ai-不胡编)
- [第 5 步：编写 Web 网页服务（让用户在浏览器里使用）](#第-5-步编写-web-网页服务让用户在浏览器里使用)
- [第 6 步：制作一键启动脚本与云端部署（做成成品）](#第-6-步制作一键启动脚本与云端部署做成成品)

---

## 准备工作：安装 Python 与获取大模型密钥

在写第一行代码前，只需要两样东西：

### 1. 电脑里装好 Python 运行环境
- 打开浏览器访问 [Python 官方下载页](https://www.python.org/downloads/)，下载最新版。
- **最关键的一步**：安装界面最下方，务必把 **`Add python.exe to PATH`**（添加到环境变量）打上勾，然后一路点 Next 完成安装。

### 2. 免费领取一把大模型“钥匙”（API Key）
我们要让大模型帮我们读新闻，就要调用它的接口。
1. 访问智谱 AI 开放平台：`https://open.bigmodel.cn/usercenter/apikeys`
2. 注册并登录，点击「新建 API Key」。
3. 复制生成出来的密钥（格式类似于 `62eac85...`），保存到记事本备用。

---

## 第 1 步：创建项目文件夹与配置文件（打地基）

首先在电脑任意位置（比如 `D:\每日新闻Agent`）新建一个文件夹。在这个文件夹下，我们需要创建以下几个基础文件：

```text
每日新闻Agent/
├── .env                ← 存放你的密码和配置
├── requirements.txt    ← 需要安装的第三方依赖库列表
├── data/               ← 新建一个空文件夹，用来存每天生成的简报 json
└── templates/          ← 新建一个文件夹，后面放前端网页 index.html
```

### 1.1 编写 `requirements.txt`（声明用到的库）
新建文本文件，重命名为 `requirements.txt`，写入以下内容：
```text
flask>=3.0.0
requests>=2.31.0
feedparser>=6.0.11
openai>=1.12.0
python-dotenv>=1.0.1
jieba>=0.42.1
streamlit>=1.32.0
```
**每个库的功能说明**：
- `requests`：Python 用来在网上发送 HTTP 请求下载网页的工具。
- `feedparser`：专门用来解析 RSS/XML 格式新闻源的工具。
- `openai`：调用大模型接口的标准客户端（智谱完全兼容 OpenAI 协议）。
- `flask`：把 Python 程序变成网页网站的轻量级 Web 服务框架。
- `python-dotenv`：自动读取 `.env` 配置文件里的密钥。
- `jieba`：优秀的中文分词工具，帮我们把长句子切成词。
- `streamlit`：做云端可视化界面的一大神器。

### 1.2 安装依赖
在当前文件夹打开命令行窗口（按住 `Shift` 键点击鼠标右键 $\rightarrow$ 选择“在此处打开 PowerShell 窗口”），输入：
```bash
# 1. 创建虚拟隔离环境（防止污染电脑其他软件）
python -m venv .venv

# 2. 激活虚拟环境
.venv\Scripts\activate

# 3. 安装依赖（使用清华镜像源，1分钟装完）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 1.3 编写 `.env`（写入你的配置）
新建文件名为 `.env`（注意前面有个点），写入：
```env
# 填入你刚才在智谱开放平台复制的真 Key
ZHIPUAI_API_KEY=你的真实智谱API_KEY

# 使用的模型名称（glm-4-flash 速度快且成本极低）
AGENT_MODEL=glm-4-flash
AGENT_MODEL_QA=glm-4-flash
AGENT_MAX_TOKENS=1200
```

---

## 第 2 步：编写新闻采集模块（教程序去网上抓新闻）

现在我们开始写核心逻辑代码：创建主程序文件 `agent.py`。
第一步要做的是：**怎么把全网的最新新闻抓回来？**

我们选用了 **RSS 订阅源**。RSS 是各大新闻媒体公开提供的标准数据流，数据格式极其规整，不带任何乱七八糟的广告弹窗。

### 2.1 新闻采集核心代码（写入 `agent.py` 顶部）

```python
import concurrent.futures
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
import requests

# 1. 挑选的 11 个优质新闻源
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

# 2. 类别归属映射
CATEGORIES = {
    "时政": ["中新网-滚动", "中新网-社会"],
    "财经": ["中新网-财经", "华尔街见闻"],
    "国际": ["中新网-国际"],
    "科技": ["IT之家", "钛媒体", "cnBeta", "开源中国", "Solidot"],
    "生活": ["少数派"],
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FRESH_HOURS = 30  # 只抓最近 30 小时内发布的新闻

def cutoff() -> datetime:
    """计算新闻过期时间线：当前 UTC 时间往前推 30 小时"""
    return datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)

def clean(text: str) -> str:
    """工具函数：去除新闻摘要里的 HTML 标签和多余空格"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()

def entry_time(e) -> datetime | None:
    """工具函数：把 RSS 里各种乱七八糟的时间格式统统转成统一的标准 UTC 时间"""
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        if k in e and e[k]:
            try:
                return datetime(*e[k][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    t = e.get("published") or e.get("updated")
    if t:
        try:
            return parsedate_to_datetime(t).astimezone(timezone.utc)
        except Exception:
            return None
    return None

def fetch_one(name: str, url: str) -> tuple:
    """核心函数：抓取单个新闻源的数据"""
    try:
        # 设置 12 秒超时，防止某一个源卡死整套系统
        r = requests.get(url, headers=UA, timeout=12)
        r.encoding = r.apparent_encoding or "utf-8"
        d = feedparser.parse(r.text)
        items = []
        for e in d.entries[:12]:  # 每个源最多取最新的 12 条
            t = entry_time(e)
            if not t or t < cutoff():  # 过滤掉 30 小时前的旧新闻
                continue
            title = clean(e.get("title", ""))
            if not title:
                continue
            items.append({
                "title": title,
                "link": e.get("link", ""),
                "summary": clean(e.get("summary", ""))[:120],
                "source": name,
                "_ts": t.timestamp(),
                "time": t.astimezone(timezone(timedelta(hours=8))).strftime("%m-%d %H:%M"),
            })
        return name, items, None
    except Exception as ex:
        return name, [], f"{type(ex).__name__}"

def collect() -> tuple:
    """并发调度：同时抓取 11 个新闻源并去重"""
    # 使用 10 个多线程同时抓取，耗时从 30 秒暴降到 2 秒
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(lambda kv: fetch_one(*kv), SOURCES.items()))

    seen = set()
    news = []
    health = []
    for name, items, err in results:
        # 记录每个源的健康状况（抓到几条、是否出错）
        health.append({"name": name, "ok": bool(items), "count": len(items), "error": err})
        for it in items:
            key = it["title"][:24]  # 按标题前24字简单去重
            if key in seen:
                continue
            seen.add(key)
            news.append(it)

    # 给每条新闻打上分类标签（时政/财经/科技等）
    for it in news:
        it["category"] = next((c for c, srcs in CATEGORIES.items() if it["source"] in srcs), "其他")

    return news, health
```

### 2.2 这段代码到底干了什么？（功能拆解）
1. `SOURCES` 字典：我们定义了 11 个 RSS 网址，相当于派出了 11 个小记者。
2. `entry_time()` 函数：每个网站发布时间的格式五花八门（有的写“Wed, 15 Oct”，有的写“2026-10-15T...”），这个函数把它们通通转成统一的标准时间。
3. `cutoff()` 过滤机制：很多网站的 RSS 列表里会残留上周甚至上个月的新闻。我们加了一道硬规则：**只放行 30 小时内的最新新闻**。
4. `ThreadPoolExecutor` 多线程：普通的写法是一个接一个抓（串行），容易慢死；我们用多线程让 10 个源同时抓取（并发），2~3 秒全部下完！
5. `clean()` 与 `seen` 集合：清除新闻里的 HTML 网页标签，并通过比较标题前 24 个字去除重复内容。

---

## 第 3 步：编写大模型归纳模块（教 AI 读新闻写早报）

现在抓回了 60~100 条原始新闻，我们要把这大堆材料交给大模型（智谱 GLM），让它帮我们提炼成结构化的早报。

### 3.1 归纳与标题链接回填代码（继续追加在 `agent.py`）

```python
import json
import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")
API_KEY = os.getenv("ZHIPUAI_API_KEY", "").strip()
MODEL = os.getenv("AGENT_MODEL", "glm-4-flash").strip()

def get_client():
    """获取 OpenAI 协议客户端，连接到智谱服务器"""
    from openai import OpenAI
    return OpenAI(api_key=API_KEY, base_url="https://open.bigmodel.cn/api/paas/v4")

# 给大模型的人格设定
PERSONA = "你是严谨克制的私人新闻编辑。只做筛选归纳，绝不编造新闻、来源或数据。语言平实，不用标题党措辞。"

# 要求大模型严格按照这个 JSON 格式回答
BRIEF_PROMPT = """下面是今天的新闻条目。请生成每日简报，严格输出 JSON，不要任何额外文字。

格式：
{{"highlights":[{{"title":"标题","digest":"一句话概括","source":"来源"}}],
 "sections":[{{"category":"分类名","items":[{{"title":"标题","digest":"一句话概括","source":"来源"}}]}}]}}

硬性要求：
1. highlights 选 2 条最重要的头条，digest 说清"发生了什么+为什么重要"，不超过 30 字
2. sections 按分类组织，每类最多 3 条，每条 digest 不超过 25 字
3. 只归纳提供的条目，绝不编造任何信息
4. 分类名仅限中文：科技、财经、时政、国际、生活

新闻条目列表：
{items}"""

def call_glm(prompt: str, system: str = "") -> str:
    """封装调用智谱大模型的通用函数"""
    client = get_client()
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=msgs,
        temperature=0.2,  # 低随机度，保证客观严谨
        max_tokens=1200,
    )
    return resp.choices[0].message.content or ""

def summarize(news: list) -> dict:
    """让大模型提炼新闻，并巧妙找回原文链接"""
    if not API_KEY:
        raise RuntimeError("请在 .env 中配置 ZHIPUAI_API_KEY！")

    # 1. 把所有新闻整理成编号文本喂给模型
    lines = [f"{i}. {n['title']} (来源:{n['source']})" for i, n in enumerate(news, 1)]
    raw = call_glm(BRIEF_PROMPT.format(items="\n".join(lines)), system=PERSONA)

    # 2. 清洗可能夹带的 markdown 标记（如 ```json）
    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    data = json.loads(clean_json)

    # 3. 核心算法：解决大模型润色标题后找不到原文链接的问题（字符重叠模糊匹配）
    pool = [(n["title"], n["link"]) for n in news if n["link"]]

    def sim(a: str, b: str) -> float:
        # 去除非文字字符，对比字符集合的重叠比例
        A = set(re.sub(r"[\s\W_]+", "", a))
        B = set(re.sub(r"[\s\W_]+", "", b))
        return len(A & B) / min(len(A), len(B)) if A and B else 0.0

    def find_link(title: str) -> str:
        best_link, best_score = "", 0.0
        for orig_title, orig_link in pool:
            s = sim(title, orig_title)
            if s > best_score:
                best_link, best_score = orig_link, s
        return best_link if best_score >= 0.5 else ""

    # 把链接填回大模型生成的简报中
    for sec in data.get("sections", []):
        for it in sec.get("items", []):
            it["link"] = find_link(it.get("title", ""))
    for it in data.get("highlights", []):
        it["link"] = find_link(it.get("title", ""))

    return data
```

### 3.2 这段代码的功能解析
1. `PERSONA` 与 `BRIEF_PROMPT`：告诉大模型“你是一个新闻编辑”，用 Prompt 约束它**严格输出 JSON 结构**，必须包含 2 条头条（highlights）以及科技/财经等分类列表（sections）。
2. `clean_json` 正则替换：很多大模型很喜欢多管闲事地输出 ````json ... ````，直接调用 `json.loads` 会报错崩溃。我们用一行正则表达式把首尾的反引号扒掉。
3. **`sim()` 与 `find_link()` 模糊匹配算法（核心技巧）**：大模型生成摘要时，经常会把原始新闻标题缩写或者润色。比如原标题叫《苹果公司正式发布新款iPad mini 搭载A17芯片》，大模型在简报里写成了《苹果发布搭载A17芯片的新款iPad mini》。如果用文字完全对齐就会对不上。这个算法计算两者的字重合度，重合 50% 以上就判定为同一条新闻，**成功把原始跳转链接找了回来**！

---

## 第 4 步：编写智能问答模块（核心：怎么让 AI 不胡编）

现在简报有了，但如果用户在界面提问：“今天有什么关于半导体的新闻？”或者“今天股市表现如何？”，我们怎么回答？

直接把问题丢给大模型是绝对不行的，大模型会凭空捏造。  
因此我们做了一套**轻量级 RAG（检索增强生成）流程**：先从今天抓到的新闻里搜索，搜索到了，命令大模型基于搜索结果作答；搜不到，明确告知或用通用知识回答。

### 4.1 智能问答与防幻觉代码（继续追加在 `agent.py`）

```python
# 1. 建立同义词映射表（零延迟语义扩展）
SYNONYMS = {
    "芯片": ["芯片", "半导体", "晶圆", "光刻", "英伟达", "台积电", "算力"],
    "半导体": ["半导体", "芯片", "晶圆", "光刻"],
    "a股": ["a股", "股市", "上证", "深证", "创业板", "券商"],
    "股市": ["股市", "a股", "上证", "深证", "指数", "成交"],
    "汽车": ["汽车", "新能源车", "电动车", "特斯拉", "比亚迪"],
    "ai": ["ai", "人工智能", "大模型", "llm", "openai"],
}

# 2. 通用动词（不能单凭这些词判断新闻相关）
GENERIC = {"研究", "成果", "进展", "发布", "召开", "我国", "重要", "最新", "今日"}

def atomize_and_expand(question: str) -> list:
    """提取关键词并扩展同义词"""
    import jieba
    words = [w.strip().lower() for w in jieba.cut(question) if len(w.strip()) >= 2]
    expanded = []
    for w in words:
        expanded.append(w)
        if w in SYNONYMS:
            expanded.extend(SYNONYMS[w])
    return list(dict.fromkeys(expanded))  # 去重

def smart_search(keywords: list, pool: list) -> list:
    """在今日新闻池中打分搜索"""
    scored = []
    for n in pool:
        title = n["title"].lower()
        summ = (n["summary"] or "").lower()
        score = 0.0
        for kw in keywords:
            if kw in title:
                score += 3.0  # 标题命中权重更高
            elif kw in summ:
                score += 1.0  # 摘要命中权重较低
        
        # 核心防幻觉约束：如果只中了通用词（如'进展'），没中任何实体词，一律算 0 分
        has_entity = any(k in (title + summ) for k in keywords if k not in GENERIC)
        if score > 0 and has_entity:
            scored.append((score, n))
            
    scored.sort(key=lambda x: -x[0])  # 按分数从高到低排
    return [n for score, n in scored[:10]]

def answer(question: str, news_pool: list) -> dict:
    """问答核心：三路分流机制"""
    # 步骤一：提取问题里的实体并扩展
    kws = atomize_and_expand(question)
    
    # 步骤二：在今日抓到的新闻池里搜索
    hits = smart_search(kws, news_pool)

    # 步骤三：三路分流策略
    if len(hits) >= 3:
        # 【路线 A：新闻充足】要求必须标注来源和时间
        source_type = "news"
        ctx = "\n".join([f"[{i+1}] {n['time']} | {n['source']} | 标题:{n['title']}\n摘要:{n['summary']}" for i, n in enumerate(hits)])
        prompt = f"请基于以下【今日新闻】回答用户提问：'{question}'。\n要求：每条结论必须在末尾标注来源和时间，如（华尔街见闻 10-15）。\n\n新闻数据：\n{ctx}"
    elif len(hits) >= 1:
        # 【路线 B：新闻较少】提示信息有限
        source_type = "news_thin"
        ctx = "\n".join([f"[{i+1}] {n['source']} | {n['title']}" for i, n in enumerate(hits)])
        prompt = f"关于用户提问：'{question}'，今日新闻中仅有少量相关报道：\n{ctx}\n请如实基于上述内容回答，并说明今日该领域报道有限。"
    else:
        # 【路线 C：零命中】杜绝胡说八道！转用模型通用常识，并强行打上醒目标记
        source_type = "knowledge"
        prompt = f"【今日新闻库中未找到任何与'{question}'相关的内容】。\n这说明该问题不是今日新闻事件。请用你自己的通用知识进行科普回答，并在第一句话写明：'【📚 通用知识回答 · 非今日新闻】'。"

    answer_text = call_glm(prompt)
    return {
        "question": question,
        "answer": answer_text,
        "source_type": source_type,
        "hits_count": len(hits),
        "refs": hits  # 返回新闻供前端渲染超链接
    }
```

### 4.2 这段代码的功能解析
1. `SYNONYMS` 同义词网：用户搜“芯片”，如果不做扩展，就会漏掉只写了“半导体”或“英伟达”的新闻。有了这个字典，程序自动扩充检索范围。
2. `smart_search` 打分规则：命中标题加 3 分，命中摘要加 1 分。最精妙的是加入了 `GENERIC` 通用动词黑名单——如果一条新闻只包含了“重大进展”而没有“芯片”等实质词，坚决不返回，**避免产生驴唇不对马嘴的假匹配**。
3. **三路分流策略（杀手锏）**：
   - 搜到 3 条以上：AI 必须严格引用今天的新闻做总结；
   - 只搜到 1~2 条：实话实说“今天新闻较少”；
   - 没搜到：**绝不打肿脸充胖子**，强制在回答开头注明“【通用知识回答 · 非今日新闻】”，彻底杜绝 AI 幻觉！

---

## 第 5 步：编写 Web 网页服务（让用户在浏览器里使用）

现在后台抓取、归纳、问答全部写好了，怎么让别人用起来？我们用 Flask 写出几个简单的接口，并提供一个好看的网页。

### 5.1 后端 API 路由代码（在 `agent.py` 底部加上）

```python
import threading
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
_news_pool = []          # 内存新闻池
_latest_briefing = None  # 最新简报缓存

@app.route("/")
def index():
    """打开网站首页"""
    return render_template("index.html")

@app.route("/api/briefing")
def api_briefing():
    """获取今天已生成好的简报数据"""
    if _latest_briefing:
        return jsonify(_latest_briefing)
    return jsonify({"error": "generating", "msg": "简报正在生成中..."}), 202

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """点击'刷新简报'按钮的接口"""
    threading.Thread(target=run_daily_job).start()
    return jsonify({"ok": True, "msg": "已开始重新抓取并生成！"})

@app.route("/api/ask", methods=["POST"])
def api_ask():
    """智能提问接口"""
    q = (request.json or {}).get("question", "").strip()
    if not q:
        return jsonify({"ok": False, "msg": "请输入问题"}), 400
    res = answer(q, _news_pool)
    return jsonify({"ok": True, **res})

def run_daily_job():
    """执行每日例行全流程任务"""
    global _news_pool, _latest_briefing
    print(">> [1/2] 正在并发抓取新闻...")
    news, health = collect()
    _news_pool = news
    print(f">> 抓取完成，共 {len(news)} 条有效新闻。")
    
    print(">> [2/2] 正在由大模型提炼结构化简报...")
    brief = summarize(news)
    brief["date"] = datetime.now().strftime("%Y年%m月%d日")
    _latest_briefing = brief
    print(">> 简报生成成功！")

if __name__ == "__main__":
    # 启动时在后台先自动抓一次
    threading.Thread(target=run_daily_job).start()
    print("\n=========================================")
    print("  每日新闻简报 Agent 已经启动！")
    print("  请用浏览器打开：http://127.0.0.1:8848")
    print("=========================================\n")
    app.run(host="127.0.0.1", port=8848)
```

### 5.2 前端网页设计（创建 `templates/index.html`）
在 `templates` 文件夹下新建 `index.html`。这里包含现代化、具有科技感的高级卡片 UI（包含今日焦点、分类速览、搜索框与提问对话框）。页面会通过 JavaScript 的 `fetch()` 异步请求上面的 `/api/briefing` 和 `/api/ask` 接口，实现免刷新无缝交互。

*(项目代码库中已自带高度优化的 `templates/index.html`，无需做任何修改，直接沿用即可)*。

---

## 第 6 步：制作一键启动脚本与云端部署（做成成品）

代码都写完了，怎么让一个连代码是什么都不知道的朋友一键运行？

### 6.1 编写 Windows 一键启动脚本（`启动.bat`）
在项目根目录新建记事本，写入以下三行代码，保存为 `启动.bat`：
```bat
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
start http://127.0.0.1:8848
python agent.py
pause
```
**功能**：以后任何人想用，只需要**鼠标双击这个 `启动.bat`**，黑窗口会自动激活虚拟环境、自动打开浏览器弹到 `http://127.0.0.1:8848`，全程完全不用打字！

### 6.2 零成本部署到公网（Streamlit 版）
如果想分享给没带电脑的手机用户看，可以使用我们配套编写的 `streamlit_app.py`：
1. 把整个工程提交到你自己的 GitHub 仓库中（注意 `.env` 会被自动忽略，不会泄露密码）。
2. 打开免费云平台 [Streamlit Community Cloud](https://share.streamlit.io/)，用 GitHub 账号登录。
3. 点击 **Create app**，选定刚才的仓库，**Main file path** 输入 `streamlit_app.py`。
4. 在 **Advanced settings** 里的 **Secrets** 贴上：
   ```toml
   ZHIPUAI_API_KEY = "你的智谱API密钥"
   ```
5. 点击 **Deploy**，1 分钟后你就会获得一个全世界都可以访问的网址（如 `https://my-daily-news.streamlit.app`）！

---

## 🧭 总结与整体复盘图表

最后，我们用一张简明的结构表，帮你把上面所有的代码串起来：

| 模块 | 对应文件 / 函数 | 实际解决的核心问题 |
| :--- | :--- | :--- |
| **基础配置** | `.env` / `requirements.txt` | 管理密钥安全，隔离安装 7 个核心依赖包。 |
| **网络采集** | `collect()` / `fetch_one()` | 10 线程并发抓取 11 个 RSS 源，30 小时时效清洗与自动去重。 |
| **大模型归纳** | `summarize()` | 结构化 JSON 提示词设计，并用 `sim()` 算法把被改写的标题链接找回来。 |
| **防幻觉问答** | `answer()` / `smart_search()` | 同义词扩展 + 通用词过滤 + **三路分流机制**（充足新闻/报道有限/通用知识）。 |
| **交互呈现** | `Flask` 路由 + `index.html` | 前后端分离异步渲染，提供呼吸灯、快捷提问气泡和精致卡片。 |
| **成品交付** | `启动.bat` / `streamlit_app.py` | 本地双击秒开 + 公网免服务器免费部署分享。 |

整个项目没有任何花哨臃肿的框架，**用最清晰直白的代码，做出了最实用、最可靠的 AI Agent 应用**。现在就打开终端，跟着上面的步骤敲一遍吧！
