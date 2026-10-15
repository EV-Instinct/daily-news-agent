# -*- coding: utf-8 -*-
"""
每日新闻简报 Agent —— Streamlit 版入口
======================================
原工程是 Flask 应用（agent.py + templates/index.html）。
Streamlit Community Cloud 只运行 Streamlit 脚本，因此本文件负责：

  1. import agent.py，完整复用其 RSS 采集 / GLM 归纳 / 智能问答逻辑
     （agent.py 的 Flask 路由有 __main__ 保护，import 时不会启动服务）；
  2. 把 Flask 的 8 个 HTTP 接口改写为 Streamlit 原生交互；
  3. 优先从 st.secrets 读取 API Key（云端部署用），本地回落 .env。

本地运行：  .venv\\Scripts\\python.exe -m streamlit run streamlit_app.py
云端部署：  Streamlit Community Cloud，secrets 中配置 ZHIPUAI_API_KEY
"""

import json
import os
import threading
import time
from datetime import datetime

import streamlit as st


# ------------------------------------------------------------------
# secrets → 环境变量
# Streamlit Cloud 的密钥在 Web 界面填写（不进入代码仓库），
# agent.py 只认环境变量，因此必须在 import agent 之前完成注入。
# ------------------------------------------------------------------
def _inject_secrets() -> None:
    """把 st.secrets 中的配置写入环境变量；本地无 secrets 文件时静默跳过。"""
    try:
        secrets = dict(st.secrets)
    except Exception:
        secrets = {}
    for key in ("ZHIPUAI_API_KEY", "AGENT_MODEL", "AGENT_MODEL_QA",
                "AGENT_MAX_TOKENS", "AGENT_BASE_URL"):
        if key in secrets and secrets[key]:
            os.environ[key] = str(secrets[key])


_inject_secrets()

import agent  # noqa: E402  （必须在 secrets 注入之后导入）

# ------------------------------------------------------------------
# 页面基础配置
# ------------------------------------------------------------------
st.set_page_config(
    page_title="每日新闻简报",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 未配置 Key 时给出明确指引，避免后端抛出难懂的异常
if not agent.API_KEY:
    st.error(
        "未配置 ZHIPUAI_API_KEY。\n\n"
        "- **云端部署**：Streamlit Cloud → App 设置 → Secrets 中添加 "
        "`ZHIPUAI_API_KEY = \"你的Key\"`\n"
        "- **本地运行**：在项目目录创建 .env 并填入 Key（参考 .env.example）"
    )
    st.stop()

# ------------------------------------------------------------------
# 自定义样式：视觉延续原 index.html（紫粉渐变标题 + 白卡片）
# ------------------------------------------------------------------
_CSS = """
<style>
.nb-title{
  font-size:2.1rem;font-weight:600;letter-spacing:-.5px;margin:.2rem 0 .1rem;
  background:linear-gradient(100deg,#6c3bf4,#ff3d8b);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
}
.nb-meta{color:#6b6b8a;font-size:.82rem;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.nb-dot{width:3px;height:3px;border-radius:50%;background:#6b6b8a;opacity:.5;display:inline-block}
.nb-card{
  background:#fff;border-radius:14px;padding:16px 22px;margin-bottom:12px;
  box-shadow:0 2px 6px rgba(20,20,43,.06),0 10px 28px rgba(108,59,244,.08);
}
.nb-hl{border-left:5px solid #6c3bf4}
.nb-hl h4,.nb-item h4{font-size:1.02rem;font-weight:600;margin:0 0 6px;line-height:1.5}
.nb-digest{color:#6b6b8a;font-size:.88rem;line-height:1.65;margin:0}
.nb-src{display:inline-block;margin-top:8px;font-size:.72rem;font-weight:500;
  background:#eef1ff;color:#6c3bf4;padding:2px 10px;border-radius:99px}
.nb-live{color:#00c48c;font-weight:600}
.nb-filter{background:rgba(108,59,244,.09);border:1px solid rgba(108,59,244,.22);
  border-radius:10px;padding:10px 16px;margin-bottom:14px;font-size:.85rem;color:#6c3bf4}
.nb-warn{color:#ff7a29;background:rgba(255,122,41,.1);padding:3px 12px;border-radius:99px;
  font-size:.75rem;font-weight:500}
.nb-ok{color:#00c48c;background:rgba(0,196,140,.1);padding:3px 12px;border-radius:99px;
  font-size:.75rem;font-weight:600}
.nb-kw{display:inline-block;font-size:.7rem;color:#6c3bf4;background:rgba(108,59,244,.09);
  padding:2px 10px;border-radius:99px;margin-bottom:8px;font-weight:500}
.nb-kw.know{color:#0b6fb8;background:rgba(0,140,220,.10)}
.nb-kw.thin{color:#ff7a29;background:rgba(255,122,41,.12)}
.nb-kw.live{color:#00c48c;background:rgba(0,196,140,.14);font-weight:600}
.nb-item{padding:6px 0 6px 14px;border-left:3px solid #e6e6f5;margin-bottom:8px}
.nb-item a{color:#14142b;text-decoration:none}
#MainMenu{visibility:hidden}
footer{visibility:hidden}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


def _esc(text) -> str:
    """HTML 转义，防止新闻标题中的特殊字符破坏页面结构。"""
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _render_news_card(item: dict, badge_html: str = "",
                      card_cls: str = "nb-card nb-hl") -> None:
    """渲染单条新闻卡片：徽章 + 标题（可点击跳原文）+ 摘要 + 来源。"""
    title = _esc(item.get("title"))
    digest = item.get("digest") or ""
    source = item.get("source") or ""
    link = item.get("link") or ""
    title_html = (
        f'<a href="{_esc(link)}" target="_blank" rel="noopener"><h4>{title}</h4></a>'
        if link else f"<h4>{title}</h4>"
    )
    st.markdown(
        f'<div class="{card_cls}">{badge_html}{title_html}'
        + (f'<p class="nb-digest">{_esc(digest)}</p>' if digest else "")
        + (f'<span class="nb-src">{_esc(source)}</span>' if source else "")
        + "</div>",
        unsafe_allow_html=True)


def _render_answer(item: dict) -> None:
    """渲染一条问答记录：来源类型徽章 + 回答正文 + 原文链接列表。"""
    source_type = item.get("source_type", "news")
    if source_type == "live_web":
        st.markdown(
            f'<span class="nb-kw live">🌐 全网实时搜索 · '
            f'命中 {item.get("count", 0)} 条 · 极速生成</span>',
            unsafe_allow_html=True)
    elif source_type == "knowledge":
        st.markdown('<span class="nb-kw know">📚 通用知识回答 · 非近期新闻</span>',
                    unsafe_allow_html=True)
    elif source_type == "news_thin":
        st.markdown(
            f'<span class="nb-kw thin">📰 今日新闻相关较少 · '
            f'命中 {item.get("count", 0)} 条</span>',
            unsafe_allow_html=True)
    elif item.get("keywords"):
        st.markdown(
            f'<span class="nb-kw">检索：{_esc(" · ".join(item["keywords"][:8]))} '
            f'｜ 命中 {item.get("count", 0)} 条 ｜ {item.get("elapsed", 0)}s</span>',
            unsafe_allow_html=True)
    st.markdown(item.get("a") or "（无回答）")
    refs = item.get("refs") or []
    if refs:
        st.caption("原文链接")
        for r in refs:
            st.markdown(
                f"- [{_esc(r.get('source'))} {_esc(r.get('time'))}] "
                f"[{_esc(r.get('title'))}]({r.get('link', '')})")


# ------------------------------------------------------------------
# 启动引导：今天没有完整简报时，才在冷启动跑一次
# ------------------------------------------------------------------
def _read_briefing():
    """读取当前主简报（可能是全量或特定关键词）；文件不存在或损坏时返回 None。"""
    if not agent.BRIEFING.exists():
        return None
    try:
        return json.loads(agent.BRIEFING.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_full_briefing():
    """读取今日全量大早报备份。"""
    full_f = agent.DATA / "full_briefing.json"
    if not full_f.exists():
        return None
    try:
        return json.loads(full_f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _need_bootstrap() -> bool:
    """今天尚未生成过全量大早报时才需要冷启动。"""
    full_b = _read_full_briefing()
    if not full_b:
        return True
    today = datetime.now().strftime("%Y年%m月%d日")
    return full_b.get("date") != today




def _render_briefing(b: dict) -> None:
    """统一渲染整份简报：元信息 + 焦点要闻 + 分类速览 + 原文卡片 + 数据源状态。"""
    if not b:
        st.info("暂无简报内容，请点击「生成简报」或右上角「🔄 重新生成」。")
        return

    kw = b.get("keyword") or ""
    meta = (
        f'<div class="nb-meta"><span>{_esc(b.get("date"))}</span>'
        f'<i class="nb-dot"></i><span>{_esc(b.get("weekday"))}</span>'
        f'<i class="nb-dot"></i><span>{_esc(b.get("generated_at"))} 更新</span>'
        f'<i class="nb-dot"></i>'
        + (f'<span class="nb-live">● 专属专题：{_esc(kw)}</span>' if kw
           else '<span class="nb-live">● 今日全量早报</span>')
        + "</div>"
    )
    st.markdown(meta, unsafe_allow_html=True)

    if kw:
        stats_kw = b.get("stats") or {}
        st.markdown(
            f'<div class="nb-filter">当前聚焦 <b>{_esc(kw)}</b> 专属简报 · '
            f'命中 {stats_kw.get("matched", 0)} 条 · '
            f'{_esc(b.get("topic_summary") or "")}</div>',
            unsafe_allow_html=True)

    # 今日焦点 / 核心要闻
    highlights = b.get("highlights") or []
    if highlights:
        title_hl = f"**今日焦点**（{len(highlights)} 条）" if not kw else f"**【{_esc(kw)}】核心要闻**（{len(highlights)} 条）"
        st.markdown(title_hl)
        for i, x in enumerate(highlights):
            badge = (f'<span style="display:inline-block;font-size:.68rem;'
                     f'font-weight:700;letter-spacing:.08em;color:#fff;'
                     f'background:linear-gradient(135deg,#6c3bf4,#ff3d8b);'
                     f'padding:2px 10px;border-radius:99px;margin-bottom:8px">'
                     f'焦点 0{i + 1}</span>')
            _render_news_card(x, badge_html=badge, card_cls="nb-card nb-hl")

    # 分类速览（双列网格）
    sections = b.get("sections") or []
    if sections:
        total = sum(len(s.get("items") or []) for s in sections)
        st.markdown(f"**分类速览**（{total} 条）")
        cols = st.columns(2)
        for i, s in enumerate(sections):
            with cols[i % 2]:
                items = s.get("items") or []
                st.markdown(
                    f'<div class="nb-card" style="border-top:4px solid #6c3bf4;'
                    f'margin-bottom:4px"><h4 style="display:flex;align-items:center;'
                    f'gap:8px;margin:0">{_esc(s.get("category"))}'
                    f'<span class="nb-src" style="margin-top:0">{len(items)} 条</span>'
                    f"</h4></div>",
                    unsafe_allow_html=True)
                for it in items:
                    _render_news_card(it, card_cls="nb-item")

    # 数据源健康状态与耗时
    stats = b.get("stats") or {}
    dead = stats.get("dead_sources") or []
    status = (
        f'<span class="nb-warn">⚠ {len(dead)} 个数据源失效：{_esc("、".join(dead))}</span>'
        if dead else
        f'<span class="nb-ok">● {stats.get("sources_total", 11)} 个数据源全部正常</span>'
    )
    st.markdown(
        f'<div class="nb-meta" style="margin-top:14px">{status}'
        f'<i class="nb-dot"></i>'
        f'<span>本次 <b>{stats.get("collected", 0)}</b> 条 · '
        f'耗时 <b>{stats.get("elapsed", 0)}</b> 秒</span></div>',
        unsafe_allow_html=True)


# ------------------------------------------------------------------
# 页头：标题 + 重新生成按钮
# ------------------------------------------------------------------
h_left, h_right = st.columns([5, 1.2])
with h_left:
    st.markdown('<div class="nb-title">每日新闻简报</div>', unsafe_allow_html=True)
with h_right:
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button("🔄 重新生成", use_container_width=True):
        with st.spinner("正在并发抓取 11 源并并行生成全量早报…"):
            res = agent.generate("")
            if not res.get("ok"):
                st.error(res.get("msg", "生成失败"))
            else:
                st.success("早报更新成功！")
                st.rerun()

# ------------------------------------------------------------------
# 三个功能区：简报 / 关键词筛选 / 问答（用 radio 切换）
# ------------------------------------------------------------------
TABS = ["📰 今日简报", "🔍 关键词筛选", "💬 问问今天"]
if "tab" not in st.session_state:
    st.session_state.tab = TABS[0]
tab = st.radio("功能区", TABS, horizontal=True, key="tab",
               label_visibility="collapsed")

# ==================================================================
# Tab 1：今日简报（全量早报大盘）
# ==================================================================
if tab == TABS[0]:
    b = _read_full_briefing() or _read_briefing()
    if not b:
        with st.spinner("首次打开，正在为您生成今日全量早报…"):
            res = agent.generate("")
            b = res.get("payload") or _read_briefing()
    _render_briefing(b)

# ==================================================================
# Tab 2：关键词筛选与全网实时搜索
# ==================================================================
elif tab == TABS[1]:
    st.markdown("#### 🔍 关键词筛选与全网实时搜索")
    st.caption("输入任意关键词（人名、公司、行业、热点事件），支持全网实时新闻搜索并极速生成专属简报。")
    c_in, c_b1, c_b2 = st.columns([4, 1.2, 1.2])
    with c_in:
        kw = st.text_input("关键词", key="filter_kw",
                           placeholder="例如：海洋 / 海底 / 芯片 / A股 / 特斯拉 / 低空经济",
                           label_visibility="collapsed")
    with c_b1:
        btn_gen = st.button("生成简报", type="primary", use_container_width=True)
    with c_b2:
        btn_all = st.button("看全部早报", use_container_width=True)

    if btn_all:
        full_b = _read_full_briefing()
        if full_b:
            agent.BRIEFING.write_text(json.dumps(full_b, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with st.spinner("正在生成全量早报…"):
                agent.generate("")
        st.session_state.filter_kw = ""
        st.rerun()

    if btn_gen:
        if not kw.strip():
            st.warning("请输入要筛选或搜索的关键词")
        else:
            with st.spinner(f"正在全网实时检索「{kw.strip()}」并极速归纳中…"):
                res = agent.generate(kw.strip())
                if not res.get("ok"):
                    st.error(res.get("msg", "生成失败"))
                else:
                    st.rerun()

    # 关键修复：就地直接渲染简报！不用跳转，页面直接展开卡片，可顺畅向下滑动！
    briefing = _read_briefing()
    if briefing:
        st.markdown("---")
        _render_briefing(briefing)
    else:
        st.info("暂无简报，请输入关键词后点击「生成简报」。")

# ==================================================================
# Tab 3：今日新闻问答（支持流式打字机秒级上屏）
# ==================================================================
else:
    st.markdown("#### 💬 今日新闻与全网问答")
    st.caption("基于今日新闻库及全网实时搜索作答，每条结论附来源；极速流式打字机输出，支持追问。")

    for item in st.session_state.get("qa", []):
        with st.chat_message("user"):
            st.write(item["q"])
        with st.chat_message("assistant"):
            _render_answer(item)

    question = st.chat_input("问我任何今日或近期新闻，例如：海底捞最近怎么了？")
    if question:
        if agent._state["running"]:
            st.warning("早报正在生成，请稍后再问")
        else:
            # 取最近 3 轮作为上下文，支持追问
            history = []
            for item in st.session_state.get("qa", [])[-3:]:
                history.append({"role": "user", "content": item["q"]})
                history.append({"role": "assistant", "content": item["a"][:600]})

            # 用户气泡
            with st.chat_message("user"):
                st.write(question)

            # 助手实时流式输出
            with st.chat_message("assistant"):
                try:
                    t0 = time.time()
                    with st.spinner("正在检索全网最新动态…"):
                        meta, stream_gen = agent.answer_stream(question, history)

                    # 渲染来源徽章
                    st_type = meta.get("source_type", "news")
                    if st_type == "live_web":
                        st.markdown(
                            f'<span class="nb-kw live">🌐 全网实时搜索 · '
                            f'命中 {meta.get("count", 0)} 条</span>',
                            unsafe_allow_html=True)
                    elif st_type == "knowledge":
                        st.markdown('<span class="nb-kw know">📚 通用知识回答 · 非近期新闻</span>',
                                    unsafe_allow_html=True)
                    elif st_type == "news_thin":
                        st.markdown(
                            f'<span class="nb-kw thin">📰 今日新闻相关较少 · '
                            f'命中 {meta.get("count", 0)} 条</span>',
                            unsafe_allow_html=True)

                    # 流式打出答案
                    full_answer = st.write_stream(stream_gen)
                    el = round(time.time() - t0, 1)

                    # 渲染原文链接
                    refs = meta.get("refs") or []
                    if refs:
                        st.caption(f"原文链接（耗时 {el}s）")
                        for r in refs:
                            st.markdown(
                                f"- [{_esc(r.get('source'))} {_esc(r.get('time'))}] "
                                f"[{_esc(r.get('title'))}]({r.get('link', '')})")

                    # 存入历史记录
                    st.session_state.qa = st.session_state.get("qa", []) + [{
                        "q": question,
                        "a": full_answer,
                        "keywords": meta.get("keywords", []),
                        "refs": meta.get("refs", []),
                        "count": meta.get("count", 0),
                        "source_type": meta.get("source_type", "news"),
                        "elapsed": el,
                    }]
                except Exception as ex:
                    st.error(f"问答失败：{ex}")


