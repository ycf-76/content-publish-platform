@echo off
REM ===========================================================================
REM 一键启动脚本：前端 + 后端 + QR Worker
REM 双击运行，会打开3个独立窗口，关闭窗口即停服务
REM ===========================================================================
chcp 65001 >nul
title 多智能体小红书发布平台 - 启动器

set ROOT=%~dp0
set BACKEND=%ROOT%backend
set FRONTEND=%ROOT%frontend
set VENV_PY=%BACKEND%\.venv\Scripts\python.exe

echo ============================================================
echo  多智能体小红书发布平台 - 一键启动
echo  前端:   http://localhost:3001
echo  后端:   http://127.0.0.1:8000
echo  QR Worker: http://127.0.0.1:9010
echo ============================================================
echo.

REM 检查 venv 是否存在
if not exist "%VENV_PY%" (
    echo [错误] 未找到后端虚拟环境: %VENV_PY%
    echo 请先创建: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM 检查 node_modules 是否存在
if not exist "%FRONTEND%\node_modules" (
    echo [错误] 未找到前端依赖: %FRONTEND%\node_modules
    echo 请先安装: cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo [1/3] 启动 QR Worker（端口 9010）...
start "QR Worker (9010)" cmd /k "cd /d %BACKEND% && "%VENV_PY%" app\account\qr_http_worker.py 9010"

echo [2/3] 启动后端（端口 8000）...
start "Backend (8000)" cmd /k "cd /d %BACKEND% && "%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/3] 启动前端（端口 3001）...
start "Frontend (3001)" cmd /k "cd /d %FRONTEND% && npm run dev"

echo.
echo ============================================================
echo  三个服务已在新窗口启动，等待就绪后即可访问：
echo  - 前端:   http://localhost:3001
echo  - 后端:   http://127.0.0.1:8000/docs
echo  - QR Worker: http://127.0.0.1:9010/health
echo.
echo  关闭对应窗口即停止服务。本窗口可关闭。
echo ============================================================
echo.

REM 等待3秒后自动打开浏览器
timeout /t 8 /nobreak >nul
start http://localhost:3001

exit
