"""
Document Reading Tools for LangChain Agents

Six tools that implement a Query → Grep/Read → Full context → LLM flow
for both SEC filings and uploaded project documents.

Files are cached to data/filing_cache/ as plain .txt files, enabling
fast ripgrep-based search over large documents.
"""
import re
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Type, List, Any

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from data.sec_edgar import SECEdgarClient

logger = logging.getLogger(__name__)

# Cache directory for all filing and document text files
CACHE_DIR = Path(__file__).parent.parent / "data" / "filing_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Resolve the ripgrep binary at import time.
# `rg` is a shell function on this machine (Claude Code bundled ripgrep) so
# subprocess can't use it directly. We prefer a real system rg (Homebrew,
# apt, etc.) and fall back to the latest Claude Code version binary.
def _find_rg_binary() -> str:
    import shutil

    # 1. Real rg on PATH (Homebrew / system package manager)
    for candidate in ["/opt/homebrew/bin/rg", "/usr/local/bin/rg", "/usr/bin/rg"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # 2. Claude Code bundled ripgrep — pick the highest installed version
    versions_dir = Path.home() / ".local" / "share" / "claude" / "versions"
    if versions_dir.exists():
        binaries = sorted(
            (p for p in versions_dir.iterdir() if p.is_file() and os.access(p, os.X_OK)),
            key=lambda p: [int(x) for x in p.name.split(".") if x.isdigit()],
            reverse=True,
        )
        if binaries:
            logger.debug(f"Using ripgrep via Claude Code binary: {binaries[0]}")
            return str(binaries[0])

    # 3. Last resort — let subprocess raise a clear error if missing
    return "rg"

RG_BINARY = _find_rg_binary()


def _safe_filename(name: str) -> str:
    """Strip characters that are unsafe in filenames."""
    return re.sub(r"[^\w\-.]", "_", name)


# ============================================================================
# Tool 1: Fetch and Cache SEC Filing
# ============================================================================

class FetchAndCacheFilingInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol (e.g. 'AAPL')")
    filing_type: str = Field(
        default="10-K",
        description="Filing type: '10-K' (annual), '10-Q' (quarterly), '8-K' (material event)",
    )


class FetchAndCacheFilingTool(BaseTool):
    """Download a SEC filing to local cache and return its file path."""

    name: str = "fetch_and_cache_filing"
    description: str = """Download a SEC filing (10-K, 10-Q, 8-K) to local cache and return its file path.

    ALWAYS call this first before using grep_filing or read_file_section on a SEC filing.
    Returns the absolute path to the cached .txt file.

    Use this when the user asks what a filing *says* about a specific topic —
    do NOT answer from memory. Always fetch and read the actual document first."""

    args_schema: Type[BaseModel] = FetchAndCacheFilingInput

    def _run(self, ticker: str, filing_type: str = "10-K") -> str:
        try:
            client = SECEdgarClient()
            filings = client.get_recent_filings(ticker.upper(), filing_type=filing_type, limit=1)
            if not filings:
                return (
                    f"No {filing_type} filing found for {ticker} in SEC EDGAR. "
                    "The company may not be US-listed or may not have filed recently."
                )

            filing = filings[0]
            if not filing.get("primary_document"):
                return f"Filing found for {ticker} (filed {filing['filing_date']}) but primary document is missing."

            text = client.get_filing_text(
                accession_number=filing["accession_number"],
                cik=filing["cik"],
                primary_document=filing["primary_document"],
            )
            if not text:
                return (
                    f"Could not retrieve filing text for {ticker} {filing_type} "
                    f"(filed {filing['filing_date']}). The document may be in an unsupported format."
                )

            # Write to cache (overwrite if already cached)
            safe_ticker = _safe_filename(ticker.upper())
            safe_date = _safe_filename(filing["filing_date"])
            safe_type = _safe_filename(filing_type)
            path = CACHE_DIR / f"{safe_ticker}_{safe_type}_{safe_date}.txt"
            path.write_text(text, encoding="utf-8")

            return (
                f"{path}\n\n"
                f"Filing cached: {len(text):,} characters\n"
                f"Ticker: {ticker.upper()} | Type: {filing_type} | "
                f"Filed: {filing['filing_date']} | Period: {filing.get('report_date', 'N/A')}\n\n"
                "Use grep_filing to search for specific topics, or read_file_section to read a named section."
            )

        except Exception as e:
            logger.error(f"fetch_and_cache_filing error for {ticker}: {e}")
            return f"Error fetching {filing_type} filing for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, filing_type: str = "10-K") -> str:
        return self._run(ticker, filing_type)


# ============================================================================
# Tool 2: Load Project Document
# ============================================================================

class LoadProjectDocumentInput(BaseModel):
    project_id: str = Field(description="Project UUID (visible in the URL when inside a project workspace)")
    filename: str = Field(description="Filename of the uploaded document (use list_project_documents to see options)")


class LoadProjectDocumentTool(BaseTool):
    """Load an uploaded project document from the database to local cache."""

    name: str = "load_project_document"
    description: str = """Load an uploaded project document from the database to local cache.
    Returns its file path for use with grep_filing and read_file_section.

    Use this when a user asks about content in a document they uploaded to the project.
    The file path returned can then be passed to grep_filing or read_file_section."""

    args_schema: Type[BaseModel] = LoadProjectDocumentInput
    db_session_factory: Any = None

    def _run(self, project_id: str, filename: str) -> str:
        if self.db_session_factory is None:
            return "Document loading requires a database connection (db_session_factory not configured)."

        try:
            from sqlalchemy import select, or_
            from backend.models import ProjectDocument

            with self.db_session_factory() as session:
                # Case-insensitive partial match on filename
                result = session.execute(
                    select(ProjectDocument).where(
                        ProjectDocument.project_id == project_id,
                        or_(
                            ProjectDocument.filename == filename,
                            ProjectDocument.filename.ilike(f"%{filename}%"),
                        ),
                    ).limit(1)
                )
                doc = result.scalar_one_or_none()

            if not doc:
                return (
                    f"No document matching '{filename}' found in project {project_id}. "
                    "Check the exact filename."
                )

            if not doc.raw_text:
                return f"Document '{doc.filename}' exists but has no extracted text content."

            safe_proj = _safe_filename(project_id[:8])
            safe_file = _safe_filename(doc.filename)
            path = CACHE_DIR / f"doc_{safe_proj}_{safe_file}.txt"
            path.write_text(doc.raw_text, encoding="utf-8")

            return (
                f"{path}\n\n"
                f"Document loaded: {len(doc.raw_text):,} characters\n"
                f"Filename: {doc.filename} | Type: {doc.file_type} | "
                f"Uploaded: {doc.uploaded_at.strftime('%Y-%m-%d')}\n\n"
                "Use grep_filing to search for specific topics, or read_file_section to read a named section."
            )

        except Exception as e:
            logger.error(f"load_project_document error for project {project_id}, file {filename}: {e}")
            return f"Error loading document '{filename}': {str(e)}"

    async def _arun(self, project_id: str, filename: str) -> str:
        return self._run(project_id, filename)


# ============================================================================
# Tool 3: Grep Filing
# ============================================================================

class GrepFilingInput(BaseModel):
    pattern: str = Field(description="Search pattern (supports regex). Case-insensitive.")
    file_path: str = Field(description="Absolute path to the cached filing .txt file")
    context_lines: int = Field(
        default=5,
        description="Number of lines of context to show before and after each match (default 5)",
    )


class GrepFilingTool(BaseTool):
    """Search for a pattern inside a cached filing using ripgrep."""

    name: str = "grep_filing"
    description: str = """Search for a pattern inside a cached filing using ripgrep.
    Returns matching lines with surrounding context. Case-insensitive.

    Use this to find specific topics, metrics, or keywords in a large document after
    fetching it with fetch_and_cache_filing or load_project_document.

    Examples:
    - grep_filing("artificial intelligence", file_path, context_lines=10)
    - grep_filing("research and development expense", file_path, context_lines=5)
    - grep_filing("risk factors|material weakness", file_path, context_lines=8)"""

    args_schema: Type[BaseModel] = GrepFilingInput

    def _run(self, pattern: str, file_path: str, context_lines: int = 5) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}. Use fetch_and_cache_filing or load_project_document first."

            result = subprocess.run(
                [RG_BINARY, "--ignore-case", "-C", str(context_lines), pattern, str(path)],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 1:
                return f"No matches found for pattern '{pattern}' in {path.name}."
            if result.returncode not in (0, 1):
                stderr = result.stderr.strip()
                return f"Search error (code {result.returncode}): {stderr or 'unknown error'}"

            output = result.stdout
            if len(output) > 15000:
                output = output[:15000] + f"\n\n[Output truncated — {len(result.stdout):,} total chars. Refine your pattern or use read_file_section for a specific section.]"

            match_count = result.stdout.count("\n--\n") + 1 if result.stdout else 0
            return f"Matches for '{pattern}' in {path.name} ({match_count} context block(s)):\n\n{output}"

        except subprocess.TimeoutExpired:
            return f"Search timed out for pattern '{pattern}'. Try a more specific pattern."
        except Exception as e:
            logger.error(f"grep_filing error: {e}")
            return f"Error searching filing: {str(e)}"

    async def _arun(self, pattern: str, file_path: str, context_lines: int = 5) -> str:
        return self._run(pattern, file_path, context_lines)


# ============================================================================
# Tool 4: Read File Section
# ============================================================================

class ReadFileSectionInput(BaseModel):
    file_path: str = Field(description="Absolute path to the cached filing .txt file")
    start_marker: str = Field(description="Text marker where the section begins (e.g. 'Item 7', 'Research and Development')")
    end_marker: str = Field(description="Text marker where the section ends (e.g. 'Item 8', 'Sales and Marketing')")


class ReadFileSectionTool(BaseTool):
    """Read a specific section of a filing between two text markers."""

    name: str = "read_file_section"
    description: str = """Read a specific section of a filing between two text markers.

    Example: start_marker='Item 7', end_marker='Item 8' reads the MD&A section.
    Use after grep_filing reveals the section headers to use.

    Common 10-K section markers:
    - 'Item 1' → 'Item 1A'  (Business overview)
    - 'Item 1A' → 'Item 1B' (Risk Factors)
    - 'Item 7' → 'Item 7A'  (MD&A)
    - 'Item 7A' → 'Item 8'  (Quantitative disclosures about market risk)
    - 'Item 8' → 'Item 9'   (Financial Statements)"""

    args_schema: Type[BaseModel] = ReadFileSectionInput

    def _run(self, file_path: str, start_marker: str, end_marker: str) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}. Use fetch_and_cache_filing or load_project_document first."

            text = path.read_text(encoding="utf-8")
            text_lower = text.lower()
            start_marker_lower = start_marker.lower()
            end_marker_lower = end_marker.lower()

            start_idx = text_lower.find(start_marker_lower)
            if start_idx == -1:
                return (
                    f"Start marker '{start_marker}' not found in {path.name}. "
                    "Try grep_filing to find the exact section header text."
                )

            end_idx = text_lower.find(end_marker_lower, start_idx + len(start_marker_lower))
            if end_idx == -1:
                # Return from start marker to end of document (capped)
                section = text[start_idx:start_idx + 20000]
                note = f"\n\n[End marker '{end_marker}' not found — showing {len(section):,} chars from start marker to document end]"
            else:
                section = text[start_idx:end_idx]
                note = ""

            if len(section) > 20000:
                section = section[:20000]
                note = f"\n\n[Section truncated at 20,000 chars — full section is {end_idx - start_idx:,} chars. Use grep_filing to search within this section.]"

            return f"## Section: '{start_marker}' → '{end_marker}' in {path.name}\n\n{section}{note}"

        except Exception as e:
            logger.error(f"read_file_section error: {e}")
            return f"Error reading section: {str(e)}"

    async def _arun(self, file_path: str, start_marker: str, end_marker: str) -> str:
        return self._run(file_path, start_marker, end_marker)


# ============================================================================
# Tool 5: Read Full Filing
# ============================================================================

class ReadFullFilingInput(BaseModel):
    file_path: str = Field(description="Absolute path to the cached filing .txt file")


class ReadFullFilingTool(BaseTool):
    """Load an entire cached filing into context."""

    name: str = "read_full_filing"
    description: str = """Load an entire cached filing into context.

    Best for documents under 50,000 characters. For larger documents,
    use grep_filing or read_file_section instead to avoid truncation.

    Always check the character count reported by fetch_and_cache_filing
    before deciding whether to use this tool."""

    args_schema: Type[BaseModel] = ReadFullFilingInput

    def _run(self, file_path: str) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}. Use fetch_and_cache_filing or load_project_document first."

            text = path.read_text(encoding="utf-8")
            total = len(text)

            if total > 50000:
                return (
                    text[:50000]
                    + f"\n\n[Truncated — document is {total:,} total characters. "
                    "Use read_file_section for specific sections or grep_filing to search.]"
                )

            return f"## Full content of {path.name} ({total:,} characters)\n\n{text}"

        except Exception as e:
            logger.error(f"read_full_filing error: {e}")
            return f"Error reading filing: {str(e)}"

    async def _arun(self, file_path: str) -> str:
        return self._run(file_path)


# ============================================================================
# Tool 6: Follow Reference
# ============================================================================

class FollowReferenceInput(BaseModel):
    file_path: str = Field(description="Absolute path to the cached filing .txt file")
    reference: str = Field(description="Cross-reference text to find, e.g. 'Note 8', 'Item 1A', 'Schedule II'")


class FollowReferenceTool(BaseTool):
    """Follow a cross-reference in a filing, e.g. 'See Note 12' or 'Item 1A'."""

    name: str = "follow_reference"
    description: str = """Follow a cross-reference in a filing, e.g. 'See Note 12' or 'Item 1A'.
    Returns 50 lines of context around the referenced section.

    Use this when reading one section mentions 'See Note X' or 'refer to Item Y'
    and you want to jump to that referenced content."""

    args_schema: Type[BaseModel] = FollowReferenceInput

    def _run(self, file_path: str, reference: str) -> str:
        # Delegate to GrepFilingTool with large context
        grep_tool = GrepFilingTool()
        return grep_tool._run(pattern=reference, file_path=file_path, context_lines=50)

    async def _arun(self, file_path: str, reference: str) -> str:
        return self._run(file_path, reference)


# ============================================================================
# Tool registry
# ============================================================================

def get_document_tools(db_session_factory=None) -> List[BaseTool]:
    """Return all document reading tools.

    Args:
        db_session_factory: Optional synchronous SQLAlchemy session factory.
            Required for LoadProjectDocumentTool to query uploaded documents.
            Other tools (SEC filing fetch, grep, read) work without it.
    """
    return [
        FetchAndCacheFilingTool(),
        LoadProjectDocumentTool(db_session_factory=db_session_factory),
        GrepFilingTool(),
        ReadFileSectionTool(),
        ReadFullFilingTool(),
        FollowReferenceTool(),
    ]
