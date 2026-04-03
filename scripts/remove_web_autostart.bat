@echo off
REM ============================================
REM 差旅发票自动整理系统 - 删除 Web 服务开机自启动
REM
REM 用途：删除 Web 服务的开机启动任务
REM ============================================

setlocal

echo ============================================
echo 差旅发票整理系统 - 删除 Web 服务开机自启动
echo ============================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 需要管理员权限运行此脚本
    echo 请右键点击脚本，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo 正在删除 Web 服务开机启动任务...
schtasks /delete /tn "差旅发票整理-Web服务" /f

if %errorLevel% equ 0 (
    echo [成功] 已删除开机启动任务
) else (
    echo [提示] 未找到开机启动任务（可能未设置过）
)

REM 删除桌面快捷方式
if exist "%USERPROFILE%\Desktop\差旅发票整理-Web控制面板.lnk" (
    del "%USERPROFILE%\Desktop\差旅发票整理-Web控制面板.lnk"
    echo [成功] 已删除桌面快捷方式
)

echo.
echo 配置已清除！Web 服务不会再开机自动启动。
echo 如需手动启动，请运行 start_web.bat
echo.
pause
