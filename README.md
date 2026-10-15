# 每日新闻简报 Agent

跑在云端的私人新闻编辑：每天自动抓取 11 个 RSS 源，由 GLM 大模型归纳成结构化简报，并支持基于「今日新闻库」的智能问答（答不出时明确说明，绝不编造）。

## 功能

- **今日简报**：今日焦点（2 条最重要的新闻）+ 分类速览（科技 / 财经 / 国际 / 时政 / 生活），每条附原文链接
- **关键词筛选**：按关键词从今日新闻池筛选生成专题简报
- **新闻问答**：基于今日新闻库作答，每条结论标注来源与时间；问题超出今日新闻范围时，用通用知识回答并明确标注「非今日新闻」；支持追问
- **数据源健康提示**：采集后展示各源可用状态

## 本地运行

```bash
# 1. 建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 2. 配置 API Key（智谱 GLM，https://open.bigmodel.cn/usercenter/apikeys ）
copy .env.example .env   # 然后编辑 .env 填入 ZHIPUAI_API_KEY

# 3. 启动（两种模式任选）
python agent.py                                  # Flask 模式，访问 http://127.0.0.1:8848
streamlit run streamlit_app.py                   # Streamlit 模式，访问 http://127.0.0.1:8501
```

## 部署到 Streamlit Community Cloud

仓库已适配 Streamlit Cloud（入口为 `streamlit_app.py`）：

1. 打开 <https://share.streamlit.io>，登录后点 **Create app**
2. 选择本仓库、分支 `main`，**Main file path 填 `streamlit_app.py`**
3. 展开 **Advanced settings**，在 Secrets 中填入：

   ```toml
   ZHIPUAI_API_KEY = "你的智谱API Key"
   ```

4. 点 **Deploy**，约 1 分钟后得到公网链接（形如 `https://xxx.streamlit.app`），直接发给朋友即可

> Key 只存放在 Streamlit Cloud 的 Secrets 里，不进入代码仓库。

## 目录结构

```
├── agent.py             # 核心逻辑：RSS 采集 / GLM 归纳 / 智能问答 / Flask 服务
├── streamlit_app.py     # Streamlit 入口：复用 agent.py 逻辑，适配云端部署
├── templates/
│   └── index.html       # Flask 模式的前端页面
├── data/                # 运行时生成 briefing.json
├── requirements.txt     # 部署依赖
└── .env.example         # 配置模板
```

## 注意事项

- **Key 额度**：公网部署后，每位访客打开页面都会触发一次简报生成（消耗 GLM 额度），请留意智谱后台的用量
- **休眠唤醒**：Streamlit Community Cloud 免费应用闲置一段时间会休眠，首次访问需等待数十秒唤醒
- **数据时效**：问答只基于「今天」抓取的新闻，这是刻意设计——宁可说"今日没有报道"，也不用旧闻糊弄
