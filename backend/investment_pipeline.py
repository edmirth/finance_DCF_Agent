"""
Investment Decision Pipeline (Phase 3).

Wraps ResearchOrchestrator (Stage 1 — parallel research) and adds
three sequential gates that turn raw analyst findings into a
structured trade recommendation:

    Stage 1 — Parallel Research (delegated to ResearchOrchestrator)
        Fundamental + Quant + Macro + Sentiment + Risk + DCF run together.

    Stage 2 — Risk Gate
        Reads Stage 1 findings + firm mandate.
        Outputs: APPROVED / FLAGGED / VETOED + suggested_max_size_pct.

    Stage 3 — Compliance Gate
        Checks the ticker against firm-mandate restricted list.
        Outputs: CLEARED / BLOCKED.

    Stage 4 — PM Decision
        If Risk vetoed or Compliance blocked → forced HOLD.
        Otherwise: BUY/HOLD/SELL + size + horizon + conviction.
        Calls Anthropic Haiku for the prose rationale.
        Sets requires_approval=True if size > APPROVAL_THRESHOLD_PCT.

Persists verdicts into the ResearchTask row:
    - task.risk_check        ← "applied" / "blocked"
    - task.compliance_check  ← "cleared" / "blocked"
    - task.approval_status   ← "pending" if requires_approval else "not_required"
    - task.pm_synthesis      ← full JSON of decision + verdicts
    - task.status            ← "in_review" if requires_approval else "done"

Events emitted to the frontend (via emit_fn):
    - stage_start             {stage}
    - stage_complete          {stage, payload}
    - pipeline_complete       {decision}
"""
from __future__ import annotations

import logging
import statistics
from typing import Optional, Callable

from backend.research_orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------

APPROVAL_THRESHOLD_PCT = 3.0   # > 3% NAV requires Managing Partner approval
RISK_VETO_CONFIDENCE = 0.85    # bearish risk agent above this → veto
LOW_CONFIDENCE_FLAG = 0.40     # avg analyst confidence below this → flag
STRONG_CONVICTION_BULLISH_AGENTS = 3  # need >= this many bullish to call HIGH conviction


# ---------------------------------------------------------------------------
# Shared signal summary helper
# ---------------------------------------------------------------------------

def _summarize_section_sentiments(sections: dict) -> dict:
    bullish = bearish = neutral = 0
    confidences: list[float] = []
    for section in sections.values():
        sentiment = (section.get("sentiment") or "").lower()
        confidence = float(section.get("confidence") or 0.5)
        confidences.append(confidence)
        if sentiment == "bullish":
            bullish += 1
        elif sentiment == "bearish":
            bearish += 1
        else:
            neutral += 1

    avg_conf = statistics.fmean(confidences) if confidences else 0.5
    return {
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "avg_confidence": round(avg_conf, 3),
    }


# ---------------------------------------------------------------------------
# Stage 2 — Risk Gate
# ---------------------------------------------------------------------------

def evaluate_risk_gate(sections: dict, mandate: dict) -> dict:
    """
    Aggregate Stage 1 findings against the firm mandate.
    Pure-function: no DB calls, no LLM calls, deterministic.

    Returns:
      {
        "verdict": "approved" | "flagged" | "vetoed",
        "flags": [str, ...],
        "suggested_max_size_pct": float,
        "bullish_count": int,
        "bearish_count": int,
        "neutral_count": int,
        "avg_confidence": float,
      }
    """
    summary = _summarize_section_sentiments(sections)
    bullish = summary["bullish_count"]
    bearish = summary["bearish_count"]
    neutral = summary["neutral_count"]
    avg_conf = summary["avg_confidence"]
    flags: list[str] = []

    # Risk-agent specific check
    risk_section = sections.get("risk") or {}
    risk_view = (risk_section.get("sentiment") or "").lower()
    risk_conf = float(risk_section.get("confidence") or 0.5)

    if risk_view == "bearish" and risk_conf >= RISK_VETO_CONFIDENCE:
        flags.append(
            f"Risk agent strongly bearish ({risk_conf:.0%} confidence) — portfolio risk too high"
        )

    if avg_conf < LOW_CONFIDENCE_FLAG:
        flags.append(
            f"Low aggregate analyst confidence ({avg_conf:.0%}) — thesis weak"
        )

    if bearish > bullish:
        flags.append(
            f"More bearish ({bearish}) than bullish ({bullish}) signals across analysts"
        )

    # Verdict
    if risk_view == "bearish" and risk_conf >= RISK_VETO_CONFIDENCE:
        verdict = "vetoed"
    elif flags:
        verdict = "flagged"
    else:
        verdict = "approved"

    # Sizing
    max_size = float(mandate.get("max_position_pct") or 5.0)
    if verdict == "approved":
        suggested = max_size
    elif verdict == "flagged":
        suggested = max_size * 0.5
    else:
        suggested = 0.0

    return {
        "verdict": verdict,
        "flags": flags,
        "suggested_max_size_pct": round(suggested, 2),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "avg_confidence": avg_conf,
    }


# ---------------------------------------------------------------------------
# Stage 3 — Compliance Gate
# ---------------------------------------------------------------------------

def evaluate_compliance_gate(ticker: str, mandate: dict) -> dict:
    """
    Hard gate: check ticker against the firm's restricted list.
    Future: blackout periods, ESG exclusions, mandate-allowed instruments.

    Returns:
      {
        "verdict": "cleared" | "blocked",
        "reasons": [str, ...],
        "blocked_by": str | None,
      }
    """
    restricted = [str(t).upper() for t in (mandate.get("restricted_tickers") or [])]
    ticker = ticker.upper()

    if ticker in restricted:
        return {
            "verdict": "blocked",
            "reasons": [f"{ticker} is on the firm's restricted trading list"],
            "blocked_by": "restricted_list",
        }

    return {
        "verdict": "cleared",
        "reasons": [],
        "blocked_by": None,
    }


# ---------------------------------------------------------------------------
# Stage 4 — PM Decision (with LLM-written rationale)
# ---------------------------------------------------------------------------

def _build_findings_block(sections: dict) -> str:
    """Format completed findings as a markdown block for the PM prompt."""
    blocks = []
    for agent_name, section in sections.items():
        if section.get("error"):
            continue
        title = section.get("title") or agent_name
        sentiment = (section.get("sentiment") or "neutral").upper()
        confidence = float(section.get("confidence") or 0.0)
        points = section.get("key_points") or []
        if not points:
            continue
        bullets = "\n".join(f"• {p}" for p in points[:5])
        blocks.append(f"## {title} — {sentiment} ({confidence:.0%})\n{bullets}")
    return "\n\n".join(blocks) if blocks else "No analyst findings available."


def _call_pm_rationale(
    ticker: str,
    sections: dict,
    mandate: dict,
    action: str,
    sentiment: str,
    suggested_size: float,
    risk_verdict: dict,
    compliance_verdict: dict,
) -> str:
    """Call Haiku to produce the prose rationale paragraph."""
    try:
        from anthropic import Anthropic
        from backend.mandate import build_mandate_context

        mandate_block = build_mandate_context(mandate)
        findings_block = _build_findings_block(sections)
        firm = mandate.get("firm_name") or "the investment firm"

        gates_summary = (
            f"Risk gate: {risk_verdict['verdict'].upper()}"
            + (f" ({'; '.join(risk_verdict['flags'])})" if risk_verdict.get("flags") else "")
            + f". Compliance gate: {compliance_verdict['verdict'].upper()}"
            + (f" ({'; '.join(compliance_verdict['reasons'])})"
               if compliance_verdict.get("reasons") else "")
            + "."
        )

        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    f"{mandate_block}\n"
                    f"You are the Portfolio Manager at {firm}. "
                    f"You have decided: {action} {ticker}"
                    f"{f' at {suggested_size:.1f}% of NAV' if action == 'BUY' else ''}.\n\n"
                    f"GATES:\n{gates_summary}\n\n"
                    f"ANALYST FINDINGS:\n{findings_block}\n\n"
                    f"Write a 3-4 sentence rationale that:\n"
                    f"1. Justifies the {action} decision in light of the analyst findings\n"
                    f"2. Explains why the suggested size respects the firm's mandate "
                    f"(max position {mandate.get('max_position_pct', 5)}%, "
                    f"max sector {mandate.get('max_sector_pct', 25)}%)\n"
                    f"3. Names the single most important catalyst or risk to monitor\n"
                    f"4. Cites specific numbers from the findings\n\n"
                    f"No markdown headers. Plain prose. Authoritative tone."
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"[Pipeline] PM rationale LLM call failed: {e}")
        return (
            f"Decision: {action} {ticker}"
            f"{f' at {suggested_size:.1f}% NAV' if action == 'BUY' else ''}. "
            f"Sentiment {sentiment}. Risk gate {risk_verdict['verdict']}, "
            f"compliance {compliance_verdict['verdict']}."
        )


def evaluate_pm_decision(
    ticker: str,
    sections: dict,
    mandate: dict,
    risk_verdict: dict,
    compliance_verdict: dict,
) -> dict:
    """
    Combine all prior signals into a structured decision.

    Returns:
      {
        "action": "BUY" | "HOLD" | "SELL",
        "suggested_size_pct": float,
        "horizon": str,
        "conviction": "HIGH" | "MEDIUM" | "LOW",
        "rationale": str,
        "overall_sentiment": "bullish" | "bearish" | "neutral",
        "requires_approval": bool,
        "blocked": bool,
        "summary": str,
      }
    """
    # Hard blocks first
    if compliance_verdict["verdict"] == "blocked":
        reason = (
            compliance_verdict["reasons"][0]
            if compliance_verdict.get("reasons")
            else "Restricted by compliance"
        )
        rationale = f"COMPLIANCE BLOCK: {reason}. No trade can proceed."
        return {
            "action": "HOLD",
            "suggested_size_pct": 0.0,
            "horizon": mandate.get("investment_horizon", "12 months"),
            "conviction": "LOW",
            "rationale": rationale,
            "overall_sentiment": "neutral",
            "requires_approval": False,
            "blocked": True,
            "summary": rationale,
        }

    if risk_verdict["verdict"] == "vetoed":
        flags = "; ".join(risk_verdict.get("flags", ["Risk limits breached"]))
        rationale = f"RISK VETO: {flags}. Trade cannot proceed at this time."
        return {
            "action": "HOLD",
            "suggested_size_pct": 0.0,
            "horizon": mandate.get("investment_horizon", "12 months"),
            "conviction": "LOW",
            "rationale": rationale,
            "overall_sentiment": "bearish",
            "requires_approval": False,
            "blocked": True,
            "summary": rationale,
        }

    # Determine action from signal mix
    bullish = risk_verdict["bullish_count"]
    bearish = risk_verdict["bearish_count"]
    if bullish > bearish:
        action = "BUY"
        sentiment = "bullish"
    elif bearish > bullish:
        action = "SELL"
        sentiment = "bearish"
    else:
        action = "HOLD"
        sentiment = "neutral"

    suggested_size = float(risk_verdict["suggested_max_size_pct"]) if action == "BUY" else 0.0
    requires_approval = action == "BUY" and suggested_size > APPROVAL_THRESHOLD_PCT

    # Conviction calculation
    if (
        action == "BUY"
        and risk_verdict["verdict"] == "approved"
        and bullish >= STRONG_CONVICTION_BULLISH_AGENTS
        and risk_verdict["avg_confidence"] >= 0.65
    ):
        conviction = "HIGH"
    elif action == "HOLD" or risk_verdict["verdict"] == "flagged":
        conviction = "MEDIUM"
    else:
        conviction = "MEDIUM"

    # LLM-written prose rationale
    rationale = _call_pm_rationale(
        ticker=ticker,
        sections=sections,
        mandate=mandate,
        action=action,
        sentiment=sentiment,
        suggested_size=suggested_size,
        risk_verdict=risk_verdict,
        compliance_verdict=compliance_verdict,
    )

    return {
        "action": action,
        "suggested_size_pct": round(suggested_size, 2),
        "horizon": mandate.get("investment_horizon", "12 months"),
        "conviction": conviction,
        "rationale": rationale,
        "overall_sentiment": sentiment,
        "requires_approval": requires_approval,
        "blocked": False,
        "summary": rationale,  # alias used by some UI components
    }


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class InvestmentPipeline:
    """
    Sequential investment decision pipeline. Runs Stage 1 in parallel
    via ResearchOrchestrator, then Risk → Compliance → PM Decision.
    """

    def __init__(
        self,
        run_id: str,
        ticker: str,
        selected_agents: list,
        emit_fn: Callable,
        task_id: Optional[str] = None,
        task_type: str = "ad_hoc",
        triggered_by: str = "manual",
    ):
        self.run_id = run_id
        self.ticker = ticker.upper()
        self.selected_agents = selected_agents
        self.emit = emit_fn
        self.task_id = task_id
        self.task_type = task_type
        self.triggered_by = triggered_by

    # ---------- helpers ----------

    def _load_mandate(self) -> tuple[dict, Optional[str]]:
        try:
            from backend.database import SyncSessionLocal
            from backend.mandate import get_mandate_sync
            with SyncSessionLocal() as db:
                return get_mandate_sync(db, raise_on_error=True), None
        except Exception as e:
            logger.error(f"[Pipeline] Could not load mandate: {e}")
            return {}, str(e)

    def _persist_pipeline_results(
        self,
        risk_verdict: dict,
        compliance_verdict: dict,
        pm_decision: dict,
        bullish_count: int,
        bearish_count: int,
        neutral_count: int,
        mandate_loaded: bool = True,
        error_msg: Optional[str] = None,
    ) -> None:
        """Write all four pipeline outputs to the ResearchTask row."""
        if not self.task_id:
            return
        try:
            import json as _json
            from datetime import datetime as _dt
            from backend.database import SyncSessionLocal
            from backend.models import ResearchTask

            requires_approval = bool(pm_decision.get("requires_approval"))
            blocked = bool(pm_decision.get("blocked"))

            # Map verdicts to gate-status enum values used by the frontend
            risk_gate_status = (
                "blocked" if risk_verdict["verdict"] == "vetoed"
                else "cleared" if risk_verdict["verdict"] == "approved"
                else "applied"
            )
            compliance_gate_status = (
                "blocked" if compliance_verdict["verdict"] == "blocked" else "cleared"
            )
            approval_status = (
                "pending" if requires_approval
                else ("not_required" if not blocked else "not_required")
            )

            # Final task status
            if error_msg and not mandate_loaded:
                final_status = "failed"
            elif blocked:
                final_status = "done"           # decided, just couldn't trade
            elif requires_approval:
                final_status = "in_review"      # waiting for human approval
            else:
                final_status = "done"

            # Compose unified pm_synthesis JSON (extends existing schema)
            synthesis_payload = {
                "overall_sentiment": pm_decision["overall_sentiment"],
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "summary": pm_decision["rationale"],
                # Phase 3 additions:
                "action": pm_decision["action"],
                "suggested_size_pct": pm_decision["suggested_size_pct"],
                "horizon": pm_decision["horizon"],
                "conviction": pm_decision["conviction"],
                "requires_approval": requires_approval,
                "blocked": blocked,
                "rationale": pm_decision["rationale"],
                "risk_verdict": risk_verdict,
                "compliance_verdict": compliance_verdict,
            }

            with SyncSessionLocal() as db:
                task = db.query(ResearchTask).filter(ResearchTask.id == self.task_id).one_or_none()
                if not task:
                    logger.warning(f"[Pipeline] Task {self.task_id} not found for finalize")
                    return
                task.pm_synthesis = _json.dumps(synthesis_payload)
                task.overall_sentiment = pm_decision["overall_sentiment"]
                task.mandate_check = "applied" if mandate_loaded else "blocked"
                task.risk_check = risk_gate_status
                task.compliance_check = compliance_gate_status
                task.approval_status = approval_status
                task.status = final_status
                task.completed_at = _dt.utcnow()
                if error_msg:
                    task.error = error_msg
                db.commit()
        except Exception as e:
            logger.error(f"[Pipeline] Failed to persist pipeline results: {e}")

    # ---------- main run loop ----------

    def run(self) -> dict:
        """Execute the four-stage pipeline. Never raises — all errors captured."""
        # Stage 1 — delegate to ResearchOrchestrator (which handles task open/append)
        orchestrator = ResearchOrchestrator(
            run_id=self.run_id,
            ticker=self.ticker,
            selected_agents=self.selected_agents,
            emit_fn=self.emit,
            task_id=self.task_id,
            task_type=self.task_type,
            triggered_by=self.triggered_by,
        )
        result = orchestrator.run()
        sections = result.get("sections") or {}
        # The orchestrator may have created the task itself
        self.task_id = orchestrator.task_id

        # Load mandate (used by risk + compliance + PM)
        mandate, mandate_error = self._load_mandate()
        signal_summary = _summarize_section_sentiments(sections)

        # Stage 2 — Risk gate
        self.emit({"type": "stage_start", "stage": "risk_gate"})
        if mandate_error:
            risk_verdict = {
                "verdict": "vetoed",
                "flags": [f"Investment mandate unavailable: {mandate_error}"],
                "suggested_max_size_pct": 0.0,
                **signal_summary,
            }
        else:
            risk_verdict = evaluate_risk_gate(sections, mandate)
        self.emit({
            "type": "stage_complete",
            "stage": "risk_gate",
            "verdict": risk_verdict,
        })

        # Stage 3 — Compliance gate
        self.emit({"type": "stage_start", "stage": "compliance_gate"})
        if mandate_error:
            compliance_verdict = {
                "verdict": "blocked",
                "reasons": ["Investment mandate unavailable; compliance cannot clear this trade"],
                "blocked_by": "mandate_unavailable",
            }
        else:
            compliance_verdict = evaluate_compliance_gate(self.ticker, mandate)
        self.emit({
            "type": "stage_complete",
            "stage": "compliance_gate",
            "verdict": compliance_verdict,
        })

        # Stage 4 — PM Decision
        self.emit({"type": "stage_start", "stage": "pm_decision"})
        if mandate_error:
            rationale = (
                f"MANDATE UNAVAILABLE: {mandate_error}. "
                "Trade cannot proceed until mandate access is restored."
            )
            pm_decision = {
                "action": "HOLD",
                "suggested_size_pct": 0.0,
                "horizon": "unknown",
                "conviction": "LOW",
                "rationale": rationale,
                "overall_sentiment": "neutral",
                "requires_approval": False,
                "blocked": True,
                "summary": rationale,
            }
        else:
            pm_decision = evaluate_pm_decision(
                ticker=self.ticker,
                sections=sections,
                mandate=mandate,
                risk_verdict=risk_verdict,
                compliance_verdict=compliance_verdict,
            )
        self.emit({
            "type": "stage_complete",
            "stage": "pm_decision",
            "decision": pm_decision,
        })

        # Persist everything
        self._persist_pipeline_results(
            risk_verdict=risk_verdict,
            compliance_verdict=compliance_verdict,
            pm_decision=pm_decision,
            bullish_count=risk_verdict["bullish_count"],
            bearish_count=risk_verdict["bearish_count"],
            neutral_count=risk_verdict["neutral_count"],
            mandate_loaded=not mandate_error,
            error_msg=mandate_error,
        )

        # Final event
        self.emit({
            "type": "pipeline_complete",
            "task_id": self.task_id,
            "decision": pm_decision,
        })

        return {
            "sections": sections,
            "synthesis": result.get("synthesis"),
            "risk_verdict": risk_verdict,
            "compliance_verdict": compliance_verdict,
            "pm_decision": pm_decision,
            "task_id": self.task_id,
        }
