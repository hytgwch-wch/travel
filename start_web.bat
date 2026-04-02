@echo off
REM ============================================
REM 差旅发票自动整理系统 - Web 控制面板启动脚本
REM ============================================

setlocal

title 差旅发票整理系统 - Web 控制面板

echo ============================================
echo 差旅发票自动整理系统 - Web 控制面板
echo ============================================
echo.
echo 正在启动 Web 服务器...
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查 Flask
python -c "import flask" >nul 2>&1
if %errorLevel% neq 0 (
    echo [安装] 正在安装 Web 依赖...
    pip install Flask Werkzeug
)

REM 检查其他依赖
echo [检查] 验证项目依赖...
python -c "import docx" >nul 2>&1
if %errorLevel% neq 0 (
    echo [警告] 缺少部分依赖，建议运行 install.bat
)

echo.
echo ============================================
echo Web 控制面板启动中...
echo ============================================
echo.
echo 访问地址: http://127.0.0.1:5000
echo 按 Ctrl+C 停止服务器
echo.

REM 启动 Flask 应用
python web\app.py

REM 如果程序退出
if %errorLevel% neq 0 (
    echo.
    echo [错误] Web 服务器异常退出，错误代码: %errorLevel%
    pause
)
