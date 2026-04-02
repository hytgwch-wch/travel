@echo off
REM ============================================
REM 差旅发票自动整理系统 - 启动脚本
REM 用途：启动定时监控模式，自动处理新收到的发票
REM ============================================

setlocal

title 差旅发票自动整理系统

echo ============================================
echo 差旅发票自动整理系统
echo ============================================
echo.
echo 模式: 定时监控 (每小时检查一次新邮件)
echo 按 Ctrl+C 停止监控
echo.
echo ============================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo.
    pause
    exit /b 1
)

REM 检查依赖
echo 检查依赖...
python -c "import docx" >nul 2>&1
if %errorLevel% neq 0 (
    echo [警告] 缺少依赖包，正在安装...
    pip install -r requirements.txt
    if %errorLevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)

echo 依赖检查完成
echo.
echo ============================================
echo 启动定时监控...
echo ============================================
echo.

REM 启动定时监控模式
python main.py --daily

REM 如果程序退出，显示错误
if %errorLevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorLevel%
    pause
)
