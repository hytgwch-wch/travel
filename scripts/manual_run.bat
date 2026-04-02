@echo off
REM ============================================
REM 差旅发票自动整理系统 - 手动执行脚本
REM 用途：手动触发一次完整的发票处理流程
REM ============================================

setlocal

echo ============================================
echo 差旅发票自动整理系统 - 手动执行
echo ============================================
echo.

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM 切换到项目目录
cd /d "%PROJECT_DIR%"

echo 工作目录: %CD%
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)

REM 执行一次完整的处理流程
echo 开始执行处理流程...
echo.
python main.py --run

if %errorLevel% equ 0 (
    echo.
    echo [成功] 处理完成
) else (
    echo.
    echo [错误] 处理失败，错误代码: %errorLevel%
)

echo.
pause
