# Web Interface Setup Guide

This guide will help you set up and run the web-based chat interface for the Financial Analysis Agents.

## Architecture

The web interface consists of two parts:

1. **Backend**: FastAPI server (`backend/api_server.py`) that exposes the agents via REST API with Server-Sent Events (SSE) for streaming responses
2. **Frontend**: React + TypeScript application (`frontend/`) with a clean, modern UI

## Prerequisites

- Python 3.8+ (for backend)
- Node.js 18+ and npm (for frontend)
- All API keys configured in `.env` file (see main README.md)

## Quick Start

### 1. Start the Backend Server

```bash
# From the project root directory
cd backend

# Install Python dependencies
pip install -r requirements.txt

# Start the FastAPI server
python api_server.py
```

The backend will start on `http://localhost:8000`

You can view the auto-generated API documentation at `http://localhost:8000/docs`

### 2. Start the Frontend

Open a new terminal window:

```bash
# From the project root directory
cd frontend

# Install Node dependencies (first time only)
npm install

# Start the development server
npm run dev
```

The frontend will start on `http://localhost:3000`

### 3. Open Your Browser

Navigate to `http://localhost:3000` to use the Financial Analyst chat interface.

## Features

### Agent Selection

The interface provides access to all four agents:

- **📊 DCF Analyst** - Fast quantitative valuation
- **📈 Equity Analyst** - Comprehensive research reports
- **🔍 Research Assistant** - Interactive exploration
- **🌐 Market Analyst** - Market conditions and sentiment

Switch between agents using the dropdown in the top-right corner.

### Chat Interface

- **Clean Design** - Minimalist interface inspired by modern chat applications
- **Streaming Responses** - See responses appear in real-time as the agent generates them
- **Markdown Support** - Properly formatted tables, code blocks, lists, and more
- **Example Prompts** - Click suggested prompts to get started quickly
- **Conversation History** - Full chat history maintained per agent session

### Real-time Features

- Server-Sent Events (SSE) for streaming responses
- Loading indicators while agent is processing
- Smooth animations and transitions
- Auto-scroll to latest message

## Development

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start dev server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Backend Development

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
python api_server.py
```

The FastAPI server includes auto-reload, so changes to the backend code will automatically restart the server.

## Configuration

### Backend Configuration

The backend server can be configured in `backend/api_server.py`:

- **Host**: Default `0.0.0.0` (line 226)
- **Port**: Default `8000` (line 227)
- **CORS Origins**: Frontend URLs allowed to access the API (line 30)
- **Default Model**: `gpt-4-turbo-preview` (can be changed per request)

### Frontend Configuration

The frontend proxy configuration is in `frontend/vite.config.ts`:

- API requests to `/api/*` are proxied to `http://localhost:8000`
- Development server port: `3000`

## API Endpoints

The backend provides the following endpoints:

### GET `/`
Health check and service info

### GET `/agents`
List all available agents with descriptions

### GET `/health`
Detailed health check including API key status

### POST `/chat`
Non-streaming chat endpoint (returns complete response)

**Request body:**
```json
{
  "message": "What is Apple's intrinsic value?",
  "agent_type": "dcf",
  "model": "gpt-4-turbo-preview",
  "session_id": "optional"
}
```

### POST `/chat/stream`
Streaming chat endpoint using Server-Sent Events (SSE)

**Request body:** Same as `/chat`

**Response:** SSE stream with events:
- `start` - Analysis started
- `content` - Partial response content
- `end` - Analysis complete
- `error` - Error occurred

## Troubleshooting

### Backend Issues

**"OpenAI API key not found"**
- Ensure `.env` file exists in project root with `OPENAI_API_KEY`
- Check that you're running from the correct directory

**"Failed to create agent"**
- Verify all required API keys are set in `.env`
- Check that `FINANCIAL_DATASETS_API_KEY` and `PERPLEXITY_API_KEY` are valid

**"CORS errors" in frontend**
- Ensure frontend URL is in `allow_origins` list (line 30 in `api_server.py`)
- Check that backend server is running on port 8000

### Frontend Issues

**"npm install" fails**
- Ensure Node.js 18+ is installed: `node --version`
- Delete `node_modules` and `package-lock.json`, then retry
- Try `npm install --legacy-peer-deps`

**"Cannot connect to backend"**
- Ensure backend server is running on port 8000
- Check browser console for CORS errors
- Verify proxy configuration in `vite.config.ts`

**Streaming doesn't work**
- Some browser extensions can block SSE
- Try in incognito/private mode
- Check browser console for errors

### Performance Issues

**Agent responses are slow**
- This is expected for Equity Analyst (2-5 minutes for comprehensive analysis)
- DCF Agent is faster (~30-60 seconds)
- Research Assistant is fastest for simple queries
- Use `gpt-4o` instead of `gpt-4-turbo-preview` for faster responses

**Frontend is slow to load**
- Run production build: `npm run build && npm run preview`
- Check browser console for warnings

## Production Deployment

### Backend Deployment

For production, use a proper ASGI server like Gunicorn with Uvicorn workers:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn backend.api_server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Frontend Deployment

Build the frontend for production:

```bash
cd frontend
npm run build
```

The `dist/` folder contains the production-ready static files. Deploy to:
- Vercel
- Netlify
- AWS S3 + CloudFront
- Any static hosting service

Configure the production API URL in the frontend build.

### Environment Variables for Production

Create separate `.env.production` files:

**Backend:**
- Set proper CORS origins for your production domain
- Use environment variables for all API keys
- Enable HTTPS

**Frontend:**
- Set `VITE_API_URL` to your production backend URL

## Security Considerations

1. **Never commit `.env` file** - Contains sensitive API keys
2. **Use HTTPS in production** - Protect API keys in transit
3. **Implement rate limiting** - Prevent API abuse
4. **Add authentication** - Restrict access to authorized users
5. **Validate input** - Backend validates all requests via Pydantic models
6. **CORS configuration** - Only allow trusted origins

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Modern mobile browsers

## License

Same as main project (MIT License)

## Support

For issues with the web interface:
1. Check this guide's Troubleshooting section
2. Verify all dependencies are installed correctly
3. Check browser console and backend logs for errors
4. Ensure all API keys are valid and have sufficient quota

---

**Happy analyzing with the web interface!** 📊🚀
