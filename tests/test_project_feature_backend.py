"""Backend tests for the project workspace feature."""

from unittest.mock import MagicMock, patch

from agents.project_agent import ProjectAnalysisGraph
from backend.project_config import normalize_project_config
from data.project_memory import (
    apply_memory_patch,
    format_document_summary_entry,
    initialize_memory_doc,
    patch_memory_section,
    remove_document_summary,
    sync_project_memory,
)


class TestProjectMemoryHelpers:
    def test_initialize_memory_doc_populates_initial_tickers(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.", tickers=["NVDA", "AMD"])

        assert "## Key Companies & Tickers\n- NVDA\n- AMD" in memory_doc

    def test_patch_memory_section_append_removes_placeholder_body(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.")

        updated = patch_memory_section(
            memory_doc,
            "Uploaded Document Summaries",
            "### 10-K.pdf\nStrong backlog and expanding margins.",
            mode="append",
        )

        assert "## Uploaded Document Summaries\n### 10-K.pdf\nStrong backlog and expanding margins." in updated

    def test_apply_memory_patch_fills_extended_sections_and_clears_placeholders(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.")

        updated = apply_memory_patch(
            memory_doc,
            {
                "conclusions": ["Demand remains above supply."],
                "violated_assumptions": ["Gross margin expansion is slowing."],
                "thesis_health": {"status": "WEAKENING", "rationale": "Margin pressure offsets demand strength."},
                "assumptions": ["Hyperscaler capex remains elevated."],
                "open_questions": ["Will export controls slow shipment growth?"],
                "key_companies": ["NVIDIA (NVDA)", "AMD"],
                "live_data_snapshots": ["2026-03-15: Consensus FY revenue growth remains above 20%."],
            },
            today="2026-03-15",
            now_iso="2026-03-15T10:00:00+00:00",
        )

        assert "- [2026-03-15 - agent] Demand remains above supply." in updated
        assert "- 2026-03-15: Gross margin expansion is slowing." in updated
        assert "- Hyperscaler capex remains elevated." in updated
        assert "- NVIDIA (NVDA)" in updated
        assert "- AMD" in updated
        assert "- 2026-03-15: Consensus FY revenue growth remains above 20%." in updated
        assert "- (to be populated)" not in updated
        assert "- (none yet)" not in updated
        assert "**Status**: WEAKENING" in updated

    def test_sync_project_memory_updates_title_thesis_and_tickers(self):
        memory_doc = initialize_memory_doc("Old title", "Old thesis.")

        updated = sync_project_memory(
            memory_doc,
            title="New title",
            thesis="New thesis.",
            tickers=["msft", "nvda"],
            now_iso="2026-03-15T11:00:00+00:00",
        )

        assert updated.startswith("# Project Memory: New title")
        assert "## Thesis\nNew thesis." in updated
        assert "## Key Companies & Tickers\n- MSFT\n- NVDA" in updated
        assert "_Last updated: 2026-03-15T11:00:00+00:00_" in updated

    def test_remove_document_summary_restores_placeholder_when_last_summary_removed(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.")
        memory_doc = patch_memory_section(
            memory_doc,
            "Uploaded Document Summaries",
            "### deck.pdf\nProduct roadmap update.",
            mode="append",
        )

        updated = remove_document_summary(memory_doc, "deck.pdf")

        assert "### deck.pdf" not in updated
        assert "## Uploaded Document Summaries\n(none yet)" in updated

    def test_remove_document_summary_preserves_other_entries(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.")
        memory_doc = patch_memory_section(
            memory_doc,
            "Uploaded Document Summaries",
            "### deck.pdf\nProduct roadmap update.\n### 10-K.pdf\nCapacity plans.",
            mode="append",
        )

        updated = remove_document_summary(memory_doc, "deck.pdf")

        assert "### deck.pdf" not in updated
        assert "### 10-K.pdf" in updated

    def test_remove_document_summary_uses_document_id_for_duplicate_filenames(self):
        memory_doc = initialize_memory_doc("Semis", "AI demand remains strong.")
        memory_doc = patch_memory_section(
            memory_doc,
            "Uploaded Document Summaries",
            "\n".join(
                [
                    format_document_summary_entry("deck.pdf", "First summary.", document_id="doc-1"),
                    format_document_summary_entry("deck.pdf", "Second summary.", document_id="doc-2"),
                ]
            ),
            mode="append",
        )

        updated = remove_document_summary(memory_doc, "deck.pdf", document_id="doc-1")

        assert "<!-- project_doc:doc-1 -->" not in updated
        assert "First summary." not in updated
        assert "<!-- project_doc:doc-2 -->" in updated
        assert "Second summary." in updated


class TestProjectConfigNormalization:
    def test_normalize_project_config_merges_partial_updates(self):
        normalized = normalize_project_config(
            {"preferred_agents": ["market", "invalid", "market"]},
            existing={"tickers": ["AAPL"], "preferred_agents": ["research"], "notes": "keep me"},
        )

        assert normalized["tickers"] == ["AAPL"]
        assert normalized["preferred_agents"] == ["market"]
        assert normalized["notes"] == "keep me"

    def test_normalize_project_config_upcases_and_dedupes_tickers(self):
        normalized = normalize_project_config(
            {"tickers": ["msft", "MSFT", " nvda "]}
        )

        assert normalized["tickers"] == ["MSFT", "NVDA"]
        assert normalized["preferred_agents"] == []


class TestProjectAgentRobustness:
    def test_earnings_agent_uses_single_project_ticker_when_query_has_none(self):
        graph = ProjectAnalysisGraph()
        agent = MagicMock()
        agent.analyze.return_value = "Earnings summary"

        state = {
            "query": "What changed since the latest quarter?",
            "project_id": "project-1",
            "context_block": "<project_context>\n<project_tickers>AAPL</project_tickers>\n</project_context>",
            "routing_decision": {"agents": [{"agent_type": "earnings", "task": "Assess the latest quarter."}]},
            "agent_results": [],
            "errors": [],
            "synthesis": "",
            "memory_patch": {},
            "final_response": "",
            "start_time": 0.0,
        }

        with patch("agents.project_agent.create_earnings_agent", return_value=agent):
            result = graph.run_agent_earnings(state)

        agent.analyze.assert_called_once_with("AAPL")
        assert result["agent_results"][0]["output"] == "Earnings summary"
