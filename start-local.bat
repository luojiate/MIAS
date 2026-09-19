@echo off
set ROOT=%~dp0
sc query MongoDB | findstr /I "RUNNING" >nul
if errorlevel 1 net start MongoDB
start "MIAS-API" cmd /k "cd /d %ROOT%backend && .venv\Scripts\uvicorn.exe app:app --host 127.0.0.1 --port 8000 --reload"
start "MIAS-UI" cmd /k "cd /d %ROOT%frontend && set BROWSER=none && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
echo Frontend http://127.0.0.1:5173
echo Backend  http://127.0.0.1:8000