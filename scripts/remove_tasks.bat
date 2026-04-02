@echo off
REM ============================================
REM 差旅发票自动整理系统 - 删除 Windows 定时任务
REM ============================================

setlocal

echo ============================================
echo 差旅发票自动整理系统 - 删除定时任务
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

echo 正在删除定时任务...
echo.

REM 删除每日任务
schtasks /delete /tn "差旅发票自动整理-每日同步" /f >nul 2>&1
if %errorLevel% equ 0 (
    echo [成功] 已删除：差旅发票自动整理-每日同步
) else (
    echo [信息] 未找到：差旅发票自动整理-每日同步
)

REM 删除启动任务
schtasks /delete /tn "差旅发票自动整理-启动时" /f >nul 2>&1
if %errorLevel% equ 0 (
    echo [成功] 已删除：差旅发票自动整理-启动时
) else (
    echo [信息] 未找到：差旅发票自动整理-启动时
)

REM 删除桌面快捷方式
set SHORTCUT=%USERPROFILE%\Desktop\差旅发票整理-手动执行.lnk
if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo [成功] 已删除：桌面快捷方式
) else (
    echo [信息] 未找到：桌面快捷方式
)

echo.
echo ============================================
echo 清理完成！
echo ============================================
pause
