@echo off
REM Startup script for Financial Analyst Web Interface (Windows)
REM Starts both backend and frontend servers

echo ==========================================
echo Financial Analyst Web Interface
echo ==========================================
echo.

REM Check if .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please create .env file with your API keys.
    echo See .env.example for reference.
    exit /b 1
)

REM Check if Python virtual environment exists
if not exist venv (
    echo Virtual environment not found. Creating one...
    python -m venv venv
)

REM Activate virtual environment
echo Activating Python virtual environment...
call venv\Scripts\activate.bat

REM Install backend dependencies if needed
if not exist backend\.installed (
    echo Installing backend dependencies...
    pip install -r requirements.txt
    pip install -r backend\requirements.txt
    type nul > backend\.installed
)

REM Check if node_modules exists for frontend
if not exist frontend\node_modules (
    echo Installing frontend dependencies...
    cd frontend
    npm install
    cd ..
)

echo.
echo Starting servers...
echo.

REM Start backend server
echo Starting backend API server on http://localhost:8000...
start "Backend API" cmd /k "cd backend && python api_server.py"

REM Wait for backend to start
timeout /t 3 /nobreak > nul

REM Start frontend server
echo Starting frontend dev server on http://localhost:3000...
start "Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ==========================================
echo Servers are starting!
echo ==========================================
echo.
echo Frontend: http://localhost:3000
echo Backend API: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.
echo Close the terminal windows to stop the servers
echo.

pause
