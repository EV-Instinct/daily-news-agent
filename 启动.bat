@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行：
    echo   .venv\Scripts\python.exe -m pip install feedparser openai flask python-dotenv requests
    pause
    exit /b 1
)

if not exist ".env" (
    echo [提示] 未找到 .env 配置，正在从模板创建...
    copy /y ".env.example" ".env" >nul
    echo 已创建 .env，请填入 ZHIPUAI_API_KEY 后重新运行。
    notepad ".env"
    pause
    exit /b 1
)

echo 正在启动每日新闻简报 Agent...
start "" http://127.0.0.1:8848
".venv\Scripts\python.exe" agent.py
pause