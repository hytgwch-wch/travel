@echo off
REM ============================================
REM 差旅发票自动整理系统 - 一键安装脚本
REM
REM 用途：自动安装依赖、配置环境、设置定时任务
REM ============================================

setlocal enabledelayedexpansion

echo ============================================
echo 差旅发票自动整理系统 - 一键安装
echo ============================================
echo.
echo 此脚本将：
echo 1. 检查 Python 环境
echo 2. 安装项目依赖
echo 3. 创建配置文件
echo 4. 设置 Windows 定时任务（可选）
echo.
echo 按任意键继续，或 Ctrl+C 取消...
pause >nul

REM ============================================
REM 1. 检查 Python 环境
REM ============================================
cls
echo ============================================
echo [1/4] 检查 Python 环境
echo ============================================
echo.

python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python
    echo.
    echo 请先安装 Python 3.8 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo Python 版本: %%i
echo.

REM ============================================
REM 2. 安装项目依赖
REM ============================================
echo ============================================
echo [2/4] 安装项目依赖
echo ============================================
echo.

echo 正在安装依赖包...
pip install -r requirements.txt

if %errorLevel% neq 0 (
    echo.
    echo [警告] 部分依赖安装失败，尝试继续...
) else (
    echo.
    echo [成功] 依赖安装完成
)
echo.

REM ============================================
REM 3. 创建配置文件
REM ============================================
echo ============================================
echo [3/4] 创建配置文件
echo ============================================
echo.

if not exist "config\config.yaml" (
    echo [创建] config\config.yaml
    copy config\config.yaml.example config\config.yaml >nul 2>&1
)

if not exist "config\email.yaml" (
    echo [创建] config\email.yaml
    copy config\email.yaml.example config\email.yaml >nul 2>&1
)

if not exist "data\records.db" (
    echo [创建] data\records.db
    mkdir data >nul 2>&1
)

REM ============================================
REM 4. 询问是否设置定时任务
REM ============================================
echo ============================================
echo [4/4] 设置定时任务 (可选)
echo ============================================
echo.
echo 是否设置 Windows 定时任务？
echo 设置后可自动定期执行发票同步和处理
echo.
set /p SETUP_TASK="请输入 (Y/N): "

if /i "%SETUP_TASK%"=="Y" (
    echo.
    echo 正在启动任务配置脚本...
    echo.
    scripts\setup_task.bat
)

REM ============================================
REM 安装完成
REM ============================================
cls
echo ============================================
echo 安装完成！
echo ============================================
echo.
echo 配置文件位置:
echo   - config\config.yaml (主配置)
echo   - config\email.yaml (邮箱配置)
echo   - config\travelers.yaml (出差人信息)
echo.
echo 使用方法:
echo   - 手动执行: 双击 start.bat
echo   - 单次运行: 双击 scripts\manual_run.bat
echo   - 生成行程: python main.py --trips
echo   - 生成报销单: python fill_reimbursement_template.py
echo.
echo 下一步:
echo   1. 编辑 config\email.yaml 配置邮箱信息
echo   2. 运行 start.bat 开始使用
echo.
echo 按任意键退出...
pause >nul
