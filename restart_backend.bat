@echo off
chcp 65001 >nul
echo ========================================
echo   微信机器人 - 重启后端服务
echo ========================================
echo.

echo [1/3] 停止当前后端进程 (PID 39232)...
taskkill /PID 39232 /F >nul 2>&1
if %ERRORLEVEL%==0 (
    echo     ✓ 已停止
) else (
    echo     ⚠ 进程可能已不存在或无权限
)

echo.
echo [2/3] 等待端口释放...
timeout /t 2 /nobreak >nul

echo.
echo [3/3] 启动新的后端服务...
cd /d "%~dp0backend"
start "Backend Server" python -m uvicorn app.main:app --reload --port 8000

echo.
echo ========================================
echo   ✅ 后端重启命令已执行！
echo ========================================
echo.
echo 请等待 5-10 秒后验证：
echo   • 浏览器访问: http://localhost:8000/api/wechat/health
echo   • 应该返回 JSON 而不是 Not Found
echo.
echo 如果还是失败，请查看新弹出的窗口中的错误信息。
echo.
pause