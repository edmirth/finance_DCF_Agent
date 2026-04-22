# Deployment Guide — Finance DCF Agent

## Quick Deploy to Railway

### Prerequisites
- Railway account (https://railway.app)
- GitHub repo connected to Railway

### Step 1: Create Railway Project

1. Go to https://railway.app/new
2. Click "Deploy from GitHub repo"
3. Select `edmirth/finance_DCF_Agent`
4. Railway will auto-detect the Python project

### Step 2: Add Environment Variables

In Railway dashboard → Variables, add:

```
ANTHROPIC_API_KEY=your_anthropic_key
FINANCIAL_DATASETS_API_KEY=your_financial_datasets_key
TAVILY_API_KEY=your_tavily_key (optional, for web search)
FMP_API_KEY=your_fmp_key (optional, for additional data)
```

### Step 3: Configure Build

Railway should auto-detect from `nixpacks.toml`. If not, set:

- **Build Command:** `pip install -r requirements.txt && pip install -r backend/requirements.txt && cd frontend && npm install && npm run build`
- **Start Command:** `cd backend && uvicorn api_server:app --host 0.0.0.0 --port $PORT`

### Step 4: Deploy

Click "Deploy" — Railway will:
1. Install Python dependencies
2. Install Node dependencies  
3. Build React frontend
4. Start the FastAPI server
5. Serve frontend from `/frontend/dist`

### Step 5: Get Your URL

Railway provides a URL like: `https://finance-dcf-agent-production.up.railway.app`

---

## Alternative: Render

### Step 1: Create Web Service

1. Go to https://render.com
2. New → Web Service
3. Connect GitHub repo

### Step 2: Configure

- **Build Command:** `pip install -r requirements.txt && pip install -r backend/requirements.txt && cd frontend && npm install && npm run build`
- **Start Command:** `cd backend && uvicorn api_server:app --host 0.0.0.0 --port $PORT`

### Step 3: Environment Variables

Add the same env vars as Railway.

---

## Local Production Test

```bash
# Build frontend
cd frontend && npm run build && cd ..

# Run backend (serves frontend from dist/)
cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000

---

## Architecture

```
┌─────────────────────────────────────────┐
│            Railway / Render              │
├─────────────────────────────────────────┤
│  FastAPI Backend (port $PORT)           │
│  ├── /agents, /chat, /memo, etc.        │
│  └── Static files from frontend/dist/   │
├─────────────────────────────────────────┤
│  React Frontend (built to dist/)        │
│  └── SPA served by FastAPI              │
└─────────────────────────────────────────┘
```

---

## Troubleshooting

**Build fails on npm install:**
- Check Node version (needs 18+)
- Run `cd frontend && rm -rf node_modules && npm install`

**API errors 401/403:**
- Check environment variables are set correctly
- Verify API keys are valid

**Frontend shows blank:**
- Check browser console for errors
- Verify `frontend/dist/` exists after build

**CORS errors:**
- In production, frontend is served from same origin — no CORS needed
- For development, vite proxy handles it
