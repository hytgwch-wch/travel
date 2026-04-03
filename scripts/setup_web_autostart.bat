@echo off
REM ============================================
REM 差旅发票自动整理系统 - Web 服务开机自启动配置
REM
REM 用途：设置 Web 服务开机自动启动
REM ============================================

setlocal

echo ============================================
echo 差旅发票整理系统 - Web 服务开机自启动
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
REM 删除旧任务（如果存在）
REM ============================================
echo [1/3] 清理旧任务...
schtasks /delete /tn "差旅发票整理-Web服务" /f >nul 2>&1

REM ============================================
REM 创建开机启动任务
REM ============================================
echo.
echo [2/3] 创建 Web 服务开机启动任务...
schtasks /create /tn "差旅发票整理-Web服务" /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\web\app.py\"" /sc onlogon /ru "%USERNAME%" /rl LOW /f

if %errorLevel% equ 0 (
    echo [成功] 已创建开机启动任务（用户登录时自动启动 Web 服务）
) else (
    echo [警告] 创建启动任务失败
)

REM ============================================
REM 创建桌面快捷方式（手动启动 Web 服务）
REM ============================================
echo.
echo [3/3] 创建桌面快捷方式...

set SHORTCUT=%USERPROFILE%\Desktop\差旅发票整理-Web控制面板.lnk
set TARGET="%PYTHON_PATH%" "%PROJECT_DIR%\web\app.py"

powershell -command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%PYTHON_PATH%'; $s.Arguments = '"%PROJECT_DIR%\web\app.py"'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Save()"

if exist "%SHORTCUT%" (
    echo [成功] 已创建桌面快捷方式：差旅发票整理-Web控制面板
) else (
    echo [警告] 创建快捷方式失败
)

REM ============================================
REM 显示已创建的任务
REM ============================================
echo.
echo ============================================
echo 配置完成！
echo ============================================
echo.
echo Web 服务将在下次登录时自动启动
echo 访问地址: http://127.0.0.1:5000
echo.
echo 提示：
echo - 自动启动：用户登录时自动启动 Web 服务
echo - 手动启动：双击桌面快捷方式或运行 start_web.bat
echo - 查看任务：taskschd.msc
echo - 停止服务：运行 scripts\remove_web_autostart.bat
echo.
pause
