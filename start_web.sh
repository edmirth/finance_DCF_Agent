#!/bin/bash

# Startup script for Phronesis AI
# Starts both backend and frontend servers

echo "Starting Phronesis AI..."
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found!"
    echo "Please create .env file with your API keys."
    exit 1
fi

# Check if Python virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install backend dependencies if needed
if [ ! -f "backend/.installed" ]; then
    echo "Installing backend dependencies..."
    pip install -r requirements.txt
    pip install -r backend/requirements.txt
    touch backend/.installed
fi

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd frontend && npm install && cd ..
fi

# Clear ports before starting
clear_ports() {
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    lsof -ti :3000 | xargs kill -9 2>/dev/null || true
    lsof -ti :5173 | xargs kill -9 2>/dev/null || true
}

echo "Clearing ports..."
clear_ports
sleep 1

# Ctrl+C handler — kill by port (catches uvicorn children too)
cleanup() {
    echo ""
    echo "Shutting down..."
    clear_ports
    exit 0
}

trap cleanup INT TERM

# Start backend
echo "Starting backend on http://localhost:8000..."
cd backend
python api_server.py &
BACKEND_PID=$!
cd ..

sleep 3

# Start frontend
echo "Starting frontend on http://localhost:3000..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

wait $BACKEND_PID $FRONTEND_PID
