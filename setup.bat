@echo off
echo ==========================================
echo  AI Shorts Generator - Project Setup (Windows)
echo ==========================================
echo.

:: Check Node.js
echo Checking Node.js...
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH. Please install Node.js (v20+ recommended).
    exit /b 1
)
echo Node.js is installed.

:: Check Python
echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python (v3.10+ recommended).
    exit /b 1
)
echo Python is installed.

:: Check FFmpeg
echo Checking FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg is not installed or not in PATH. FFmpeg is required for video processing.
) else (
    echo FFmpeg is installed.
)

echo.
echo Installing Backend dependencies...
cd backend
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install backend dependencies.
    cd ..
    exit /b 1
)
cd ..

echo.
echo Installing Frontend dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install frontend dependencies.
    cd ..
    exit /b 1
)
cd ..

echo.
echo Installing Python dependencies...
python -m pip install -r ai/requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install python dependencies globally. Trying user mode...
    python -m pip install --user -r ai/requirements.txt
)

echo.
echo ==========================================
echo  Setup Completed Successfully!
echo ==========================================
echo.
echo Please ensure Ollama is installed and running:
echo   Download from https://ollama.com/ and run 'ollama run llama3:8b'
echo.
pause
