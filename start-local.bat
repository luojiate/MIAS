@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

sc query MongoDB >nul 2>&1
if not errorlevel 1 (
  net start MongoDB >nul 2>&1
) else (
  echo [warn] MongoDB service not found. Start MongoDB on 27017 manually.
)

set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"

start "MIAS-Backend" cmd /k "cd /d ""%~dp0backend"" && "%UV%" run uvicorn app:app --host 127.0.0.1 --port 8000 --reload"

set "FNM=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Schniz.fnm_Microsoft.Winget.Source_8wekyb3d8bbwe\fnm.exe"
if not exist "%FNM%" set "FNM=%LOCALAPPDATA%\fnm\fnm.exe"
if not exist "%FNM%" set "FNM=%USERPROFILE%\.local\share\fnm\fnm.exe"
if not exist "%FNM%" where fnm >nul 2>&1 && set "FNM=fnm"

if exist "%FNM%" (
  start "MIAS-Frontend" cmd /k "cd /d ""%~dp0frontend"" && "%FNM%" use 24 && set BROWSER=none && "%FNM%" exec -- pnpm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
) else (
  echo [warn] fnm not found. Using system pnpm/node on PATH.
  start "MIAS-Frontend" cmd /k "cd /d ""%~dp0frontend"" && set BROWSER=none && pnpm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
)

echo Frontend http://127.0.0.1:5173
echo Backend  http://127.0.0.1:8000
endlocal
