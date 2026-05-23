"""Watchlist CRUD API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Watchlist, WatchlistTicker

router = APIRouter(tags=["watchlists"])


class WatchlistCreate(BaseModel):
    name: str = "My Watchlist"


class TickerAdd(BaseModel):
    ticker: str
    notes: Optional[str] = None


@router.post("/watchlists", status_code=201)
async def create_watchlist(body: WatchlistCreate, db: AsyncSession = Depends(get_db)):
    """Create a new watchlist."""
    wl = Watchlist(name=body.name)
    db.add(wl)
    await db.commit()
    return {"id": wl.id, "name": wl.name, "created_at": wl.created_at.isoformat()}


@router.get("/watchlists")
async def list_watchlists(db: AsyncSession = Depends(get_db)):
    """List all watchlists with their tickers."""
    result = await db.execute(select(Watchlist).order_by(Watchlist.created_at))
    watchlists = result.scalars().all()
    out = []
    for wl in watchlists:
        tickers_result = await db.execute(
            select(WatchlistTicker)
            .where(WatchlistTicker.watchlist_id == wl.id)
            .order_by(WatchlistTicker.added_at)
        )
        tickers = tickers_result.scalars().all()
        out.append(
            {
                "id": wl.id,
                "name": wl.name,
                "created_at": wl.created_at.isoformat(),
                "tickers": [
                    {"id": t.id, "ticker": t.ticker, "notes": t.notes, "added_at": t.added_at.isoformat()}
                    for t in tickers
                ],
            }
        )
    return out


@router.get("/watchlists/{watchlist_id}/tickers")
async def get_watchlist_tickers(watchlist_id: str, db: AsyncSession = Depends(get_db)):
    """Get tickers for a specific watchlist."""
    result = await db.execute(
        select(WatchlistTicker)
        .where(WatchlistTicker.watchlist_id == watchlist_id)
        .order_by(WatchlistTicker.added_at)
    )
    tickers = result.scalars().all()
    return [
        {"id": t.id, "ticker": t.ticker, "notes": t.notes, "added_at": t.added_at.isoformat()}
        for t in tickers
    ]


@router.post("/watchlists/{watchlist_id}/tickers", status_code=201)
async def add_ticker_to_watchlist(watchlist_id: str, body: TickerAdd, db: AsyncSession = Depends(get_db)):
    """Add a ticker to a watchlist."""
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    normalized_ticker = body.ticker.upper()
    existing = await db.execute(
        select(WatchlistTicker).where(
            WatchlistTicker.watchlist_id == watchlist_id,
            WatchlistTicker.ticker == normalized_ticker,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"{normalized_ticker} already in watchlist")

    t = WatchlistTicker(watchlist_id=watchlist_id, ticker=normalized_ticker, notes=body.notes)
    db.add(t)
    await db.commit()
    return {"id": t.id, "ticker": t.ticker, "notes": t.notes, "added_at": t.added_at.isoformat()}


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}", status_code=204)
async def remove_ticker_from_watchlist(watchlist_id: str, ticker: str, db: AsyncSession = Depends(get_db)):
    """Remove a ticker from a watchlist."""
    result = await db.execute(
        select(WatchlistTicker).where(
            WatchlistTicker.watchlist_id == watchlist_id,
            WatchlistTicker.ticker == ticker.upper(),
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Ticker not found in watchlist")
    await db.delete(t)
    await db.commit()
    return Response(status_code=204)


@router.delete("/watchlists/{watchlist_id}", status_code=204)
async def delete_watchlist(watchlist_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a watchlist and all its tickers."""
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    await db.delete(wl)
    await db.commit()
    return Response(status_code=204)
