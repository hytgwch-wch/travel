@echo off
REM ============================================
REM 差旅发票自动整理系统 - Windows 任务计划程序配置脚本
REM
REM 用途：创建 Windows 定时任务，自动执行发票同步和处理
REM ============================================

setlocal

echo ============================================
echo 差旅发票自动整理系统 - 任务计划程序配置
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

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM 转换为绝对路径
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%CD%
popd

echo 项目目录: %PROJECT_DIR%
echo.

REM 获取 Python 路径
set PYTHON_CMD=python
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i
echo Python 路径: %PYTHON_PATH%
echo.

REM ============================================
REM 创建每日执行任务（每天 9:00 AM）
REM ============================================
echo.
echo [1/3] 创建每日定时任务...
schtasks /create /tn "差旅发票自动整理-每日同步" /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\main.py\" --daily" /sc daily /st 09:00 /ru "%USERNAME%" /f

if %errorLevel% equ 0 (
    echo [成功] 已创建每日定时任务（每天 9:00 AM 执行）
) else (
    echo [警告] 创建每日任务失败
)

REM ============================================
REM 创建系统启动时执行任务
REM ============================================
echo.
echo [2/3] 创建系统启动任务...
schtasks /create /tn "差旅发票自动整理-启动时" /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\main.py\" --daily" /sc onlogon /ru "%USERNAME%" /f

if %errorLevel% equ 0 (
    echo [成功] 已创建启动时任务（用户登录时执行）
) else (
    echo [警告] 创建启动任务失败
)

REM ============================================
REM 创建手动执行任务（右键即可运行）
REM ============================================
echo.
echo [3/3] 创建手动执行快捷方式...

set SHORTCUT=%USERPROFILE%\Desktop\差旅发票整理-手动执行.lnk
set TARGET="%PYTHON_PATH%" "%PROJECT_DIR%\main.py" --run

powershell -command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%PYTHON_PATH%'; $s.Arguments = '"%PROJECT_DIR%\main.py" --run'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Save()"

if exist "%SHORTCUT%" (
    echo [成功] 已创建桌面快捷方式：差旅发票整理-手动执行
) else (
    echo [警告] 创建快捷方式失败，可手动运行 scripts\manual_run.bat
)

REM ============================================
REM 显示已创建的任务
REM ============================================
echo.
echo ============================================
echo 已创建的任务列表：
echo ============================================
schtasks /query /fo list | findstr /i "差旅发票"

echo.
echo ============================================
echo 配置完成！
echo ============================================
echo.
echo 提示：
echo - 每日任务：每天 9:00 AM 自动执行
echo - 启动任务：用户登录时自动执行
echo - 手动执行：双击桌面快捷方式或运行 scripts\manual_run.bat
echo.
echo 查看任务：taskschd.msc
echo 删除任务：scripts\remove_tasks.bat
echo.
pause
