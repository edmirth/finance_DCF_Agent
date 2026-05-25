"""Investment memo API routes."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arena.output import extract_structured_memo
from arena.progress import clear_arena_queue, set_arena_queue
from arena.run import run_arena
from backend.database import get_db
from backend.models import Analysis

router = APIRouter()


_memo_ip_requests: dict = defaultdict(list)
_IP_MEMO_LIMIT = 5
_IP_WINDOW_SECONDS = 3600
_memo_daily_count = 0
_memo_daily_reset_date: Optional[str] = None
MEMO_DAILY_CAP = 50


def _check_memo_rate_limits(client_ip: str) -> None:
    """Check both per-IP and global daily caps."""
    global _memo_daily_count, _memo_daily_reset_date

    now = datetime.now(timezone.utc).timestamp()
    window_start = now - _IP_WINDOW_SECONDS
    _memo_ip_requests[client_ip] = [t for t in _memo_ip_requests[client_ip] if t > window_start]
    if len(_memo_ip_requests[client_ip]) >= _IP_MEMO_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit reached - try again later")
    _memo_ip_requests[client_ip].append(now)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _memo_daily_reset_date != today:
        _memo_daily_count = 0
        _memo_daily_reset_date = today
    _memo_daily_count += 1
    if _memo_daily_count > MEMO_DAILY_CAP:
        raise HTTPException(status_code=429, detail="Rate limit reached - try again later")


def derive_verdict(
    consensus_score: float,
    agent_signals: dict,
    next_action: str = "",
) -> tuple[str, float]:
    """Derive a BUY / WATCH / PASS verdict from the final thesis state."""
    bullish_count = sum(1 for signal in agent_signals.values() if signal.get("view") == "bullish")
    bearish_count = sum(1 for signal in agent_signals.values() if signal.get("view") == "bearish")

    if next_action == "escalate_to_human":
        return "WATCH", consensus_score
    if consensus_score >= 0.70 and bullish_count >= 3:
        return "BUY", consensus_score
    if consensus_score <= 0.40 or bearish_count >= 3:
        return "PASS", consensus_score
    return "WATCH", consensus_score


class MemoRequest(BaseModel):
    ticker: str
    query_mode: str = "full_ic"


class MemoSaveRequest(BaseModel):
    ticker: str
    verdict: str
    confidence: float
    structured_memo: dict
    checklist_answers: dict


def _run_arena_in_worker(
    query: str,
    ticker: str,
    query_mode: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> dict:
    set_arena_queue(queue, loop)
    try:
        return run_arena(query=query, ticker=ticker, query_mode=query_mode)
    finally:
        clear_arena_queue()


@router.post("/memo/stream")
async def memo_stream(request: Request, memo_request: MemoRequest):
    """Stream Investment Committee memo generation through SSE."""
    ticker = memo_request.ticker.upper().strip()
    if not ticker or len(ticker) > 5 or not ticker.isalpha():
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    fd_key = os.getenv("FINANCIAL_DATASETS_API_KEY")
    if fd_key:
        try:
            fd_resp = requests.get(
                "https://api.financialdatasets.ai/financials",
                params={"ticker": ticker, "period": "annual", "limit": 1},
                headers={"X-API-KEY": fd_key},
                timeout=10,
            )
            resp_json = fd_resp.json()
            message = f"{resp_json.get('message', '')} {resp_json.get('error', '')}".lower()
            if fd_resp.status_code == 402 or "credits" in message:
                raise HTTPException(
                    status_code=503,
                    detail="Financial data service is temporarily unavailable. Please try again later.",
                )
            if fd_resp.status_code != 200 or not resp_json.get("financials"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unable to find financial data for {ticker}. Please verify the symbol.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    client_ip = request.client.host if request.client else "unknown"
    _check_memo_rate_limits(client_ip)

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            None,
            _run_arena_in_worker,
            f"Investment analysis for {ticker}",
            ticker,
            memo_request.query_mode,
            queue,
            loop,
        )

        final_state = None
        try:
            arena_future = asyncio.wrap_future(future)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if event is None:
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    if future.done():
                        try:
                            final_state = future.result()
                        except Exception as exc:
                            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                            yield f"data: {json.dumps({'type': 'end'})}\n\n"
                            return
                        break
                    try:
                        await asyncio.wait_for(asyncio.shield(arena_future), timeout=0)
                    except asyncio.TimeoutError:
                        pass
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Analysis timed out after 3 minutes - please try again'})}\n\n"
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            return

        if final_state is None:
            try:
                final_state = await asyncio.wait_for(asyncio.wrap_future(future), timeout=180)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Analysis timed out after 3 minutes - please try again'})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                return
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                return

        structured_memo = await loop.run_in_executor(None, extract_structured_memo, final_state)
        verdict, confidence = derive_verdict(
            final_state.get("consensus_score", 0.0),
            final_state.get("agent_signals", {}),
            final_state.get("next_action", ""),
        )
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "arena_memo_ready",
                    "structured_memo": structured_memo,
                    "verdict": verdict,
                    "confidence": confidence,
                    "agent_signals": final_state.get("agent_signals", {}),
                    "debate_log": final_state.get("debate_log", []),
                }
            )
            + "\n\n"
        )
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/memo/save")
@router.post("/api/memo/save")
async def memo_save(payload: MemoSaveRequest, db: AsyncSession = Depends(get_db)):
    """Persist a completed memo with checklist answers."""
    required_keys = {"why_now", "exit_condition", "max_position_size", "quarterly_check_metric"}
    if not required_keys.issubset(payload.checklist_answers.keys()) or not all(
        str(value).strip() for value in payload.checklist_answers.values()
    ):
        raise HTTPException(status_code=422, detail="All 4 checklist fields are required to save")

    slug = secrets.token_urlsafe(6)
    content = json.dumps(
        {
            "verdict": payload.verdict,
            "confidence": payload.confidence,
            "structured_memo": payload.structured_memo,
            "checklist_answers": payload.checklist_answers,
        }
    )
    analysis = Analysis(
        ticker=payload.ticker.upper(),
        agent_type="memo",
        title=f"Investment Memo - {payload.ticker.upper()} ({payload.verdict})",
        content=content,
        tags=json.dumps(["memo"]),
        share_slug=slug,
        checklist_answers=json.dumps(payload.checklist_answers),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return {"id": analysis.id, "share_slug": slug}


@router.get("/m/{slug}")
@router.get("/api/m/{slug}")
async def memo_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    """Public read-only endpoint for a shared memo URL."""
    result = await db.execute(select(Analysis).where(Analysis.share_slug == slug))
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Memo not found")
    try:
        content = json.loads(analysis.content)
    except Exception:
        raise HTTPException(status_code=500, detail="Memo data corrupted")
    return {
        "ticker": analysis.ticker,
        "verdict": content.get("verdict"),
        "confidence": content.get("confidence"),
        "structured_memo": content.get("structured_memo"),
        "checklist_answers": content.get("checklist_answers"),
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }
