# PRD: Project Feature — Persistent Investment Thesis Workspace

## Introduction

Build a persistent, context-aware workspace where a user defines an investment thesis (e.g. "Equinor is overvalued given the oil cycle") and every subsequent analysis session inside that project is grounded in that thesis, accumulated memory, and uploaded documents.

The core value: insight compounds across sessions. Every agent query inside a project receives the full thesis, the living memory document (past conclusions, violated assumptions, thesis health), and semantically relevant chunks from uploaded documents — all assembled automatically before any analysis runs.

## Goals

- Users can create named investment projects anchored to a thesis statement
- Every chat session within a project is automatically grounded in project context
- A structured memory document accumulates conclusions, signals, and thesis health across sessions
- Uploaded documents (10-K, research reports, news) are chunked, embedded, and retrieved semantically
- A lightweight router selects and tasks the right agents per query
- All agents run in parallel via a new LangGraph graph (ProjectAnalysisGraph)
- Memory updates happen as a non-blocking async background task after each response
- Projects have a dedicated `/projects` route and sidebar section

## Architecture Overview

```
User Query
    ↓
assemble_project_context()
  ├─ project.memory_doc (SQLite)
  ├─ top-K relevant chunks (ChromaDB)
  └─ thesis + config
    ↓
route_for_project() → JSON list of agents + tasks
    ↓
ProjectAnalysisGraph (LangGraph)
  ├─ run_agent_dcf     ─┐
  ├─ run_agent_analyst  ├─ parallel
  ├─ run_agent_earnings ┤
  ├─ run_agent_market   ┤
  └─ run_agent_research ┘
    ↓ (sync)
synthesize() → final response tied to thesis
    ↓
extract_memory_patch() → patch dict
    ↓
asyncio.create_task(update_project_memory())  ← non-blocking
```

## Technical Decisions

- **Vector DB**: ChromaDB with local `all-MiniLM-L6-v2` embeddings (no API key, ~90MB download on first run)
- **UI**: New `/projects` route + `/projects/:id` workspace, sidebar Projects section above Recent Chats
- **Memory update**: `asyncio.create_task()` (same pattern as existing `_persist_conversation()`)
- **Agents in scope**: dcf, analyst, earnings, market, research — router-driven. Portfolio excluded (requires structured portfolio JSON input not applicable to a thesis workspace).

## SQLite Schema (3 new tables)

```sql
-- projects: one record per investment thesis workspace
id TEXT PK, title TEXT, thesis TEXT, config TEXT (JSON), memory_doc TEXT,
status TEXT DEFAULT 'active', created_at DATETIME, updated_at DATETIME

-- project_sessions: links sessions to a project
id TEXT PK, project_id→projects CASCADE, session_id→sessions CASCADE,
created_at DATETIME, UNIQUE(project_id, session_id)

-- project_documents: uploaded files + chroma chunk references
id TEXT PK, project_id→projects CASCADE, filename TEXT, file_type TEXT,
raw_text TEXT, chunk_count INT, chroma_ids TEXT (JSON), uploaded_at DATETIME
```

## Memory Document Schema (fixed sections)

```markdown
# Project Memory: {project_title}
_Last updated: {ISO timestamp}_

## Thesis
{thesis_statement}

## Key Assumptions
- {assumption}

## Violated or Revised Assumptions
- {date}: {what changed and why}

## Thesis Health
**Status**: STRONG | WEAKENING | CHALLENGED | INVALIDATED
**Rationale**: {one-sentence rationale}

## Key Companies & Tickers
- {TICKER}: {description}

## Accumulated Conclusions
- [{date} — {agent}] {conclusion}

## Open Questions
- {question}

## Uploaded Document Summaries
### {filename}
{200-word summary}

## Live Data Snapshots
- {TICKER}: price={x}, P/E={x}, last updated={date}
```

Sections are patched individually via regex between `## Header` and next `##`. Target ≤800 tokens.

---

## User Stories

### US-001: SQLite schema — 3 new ORM tables
**Description:** As a developer, I need the database schema for projects, project sessions, and project documents so the feature has a persistent storage foundation.

**Acceptance Criteria:**
- [x] Add `Project`, `ProjectSession`, `ProjectDocument` ORM classes to `backend/models.py` using same `Mapped`/`mapped_column` pattern as existing tables
- [x] `Project`: id (UUID), title, thesis, config (JSON Text), memory_doc (Text, default empty init), status (default 'active'), created_at, updated_at
- [x] `ProjectSession`: id, project_id (FK→Project CASCADE), session_id (FK→Session CASCADE), created_at, UNIQUE(project_id, session_id)
- [x] `ProjectDocument`: id, project_id (FK→Project CASCADE), filename, file_type, raw_text (Text), chunk_count (int), chroma_ids (JSON Text), uploaded_at
- [x] Add idempotent `CREATE TABLE IF NOT EXISTS` migration in `backend/database.py` `init_db()` (same pattern as existing `chart_specs` column migration)
- [x] Add indexes on project_id FKs and project status
- [x] Typecheck passes

---

### US-002: ChromaDB dependency + ProjectChromaClient
**Description:** As a developer, I need a ChromaDB client singleton that manages per-project collections so documents can be embedded and queried semantically.

**Acceptance Criteria:**
- [x] Add `chromadb>=0.4.0,<0.6.0` to `requirements.txt`
- [x] Create `data/chroma_client.py` with `ProjectChromaClient` singleton class
- [x] `get_or_create_collection(project_id)` returns named collection `project_{project_id}`
- [x] `add_document_chunks(project_id, document_id, filename, raw_text, chunk_size=800, chunk_overlap=100)` splits text, embeds with `DefaultEmbeddingFunction`, upserts, returns list of chroma IDs
- [x] `query(project_id, query_text, n_results=5)` returns `List[{"text": str, "source": str, "score": float}]`
- [x] `delete_chunks(project_id, chroma_ids)` deletes specific chunk IDs
- [x] `delete_collection(project_id)` drops entire collection
- [x] All sync Chroma operations wrapped for async compatibility (usable from async FastAPI handlers)
- [x] Chroma persists to `./chroma_db/` directory alongside `finance_agent.db`
- [x] Typecheck passes

---

### US-003: Memory document — initialize and patch functions
**Description:** As a developer, I need a module that creates and updates the structured memory document so project memory can be maintained across sessions.

**Acceptance Criteria:**
- [x] Create `data/project_memory.py`
- [x] `initialize_memory_doc(title: str, thesis: str) -> str` returns the empty memory document populated with thesis and placeholder sections
- [x] `patch_memory_section(memory_doc: str, section_name: str, new_content: str, mode: str = "replace") -> str` locates section by `## {section_name}` header, replaces/prepends/appends content, returns updated doc string
- [x] `SECTION_HEADERS` list defines all valid sections (same as memory doc schema above)
- [x] `update_project_memory(project_id: str, memory_patch: dict, db: AsyncSession) -> None` applies full patch dict (conclusions, violated_assumptions, thesis_health, open_questions) to project.memory_doc in SQLite with optimistic `updated_at` locking
- [x] `trim_memory_doc(memory_doc: str, max_conclusions: int = 20, max_questions: int = 10) -> str` — truncates the `Accumulated Conclusions` section to the most recent `max_conclusions` bullet entries and `Open Questions` to `max_questions` entries; all other sections left untouched; called inside `update_project_memory()` after applying patch, before writing back to SQLite
- [x] `generate_document_summary(filename: str, raw_text: str, llm) -> str` calls LLM (Haiku) to produce ≤200-word summary
- [x] Typecheck passes

---

### US-004: Context assembly middleware
**Description:** As a developer, I need a function that assembles project context from memory + ChromaDB + thesis on every query so agents always receive grounded context.

**Acceptance Criteria:**
- [ ] Create `backend/context_assembly.py`
- [ ] `assemble_project_context(project_id, query, db, chroma_client, top_k=5) -> str` function
- [ ] Returns empty string if `project_id` is None (non-project sessions unaffected)
- [ ] Loads `project.thesis`, `project.memory_doc`, `project.config` from SQLite
- [ ] Queries ChromaDB for top-K chunks relevant to `query`
- [ ] Assembles and returns XML-wrapped context block: `<project_context>...</project_context>`
- [ ] Context block sections: thesis, memory_doc, relevant document excerpts (if any), project tickers
- [ ] Total context cap: ≤3500 tokens (memory_doc ≤800, chunks ≤5×400 tokens each)
- [ ] Typecheck passes

---

### US-005: Project router — agent routing LLM call
**Description:** As a developer, I need a lightweight LLM-based router that reads a query + project context and decides which agents to invoke with what task so queries are handled by the right agents.

**Acceptance Criteria:**
- [ ] Create `backend/project_router.py`
- [ ] `route_for_project(query: str, context_block: str, project_config: dict) -> ProjectRoutingDecision` function
- [ ] `ProjectRoutingDecision` dataclass: `agents: List[AgentTask]`, `reasoning: str`
- [ ] `AgentTask` dataclass: `agent_type: str`, `task: str`
- [ ] Uses Claude Haiku (same client pattern as existing `route_agent_for_message()` in `api_server.py`)
- [ ] Router prompt selects 1–3 agents from: dcf, analyst, earnings, market, research (portfolio excluded — incompatible input format)
- [ ] Activation rules encoded in prompt: DCF/analyst for valuation, earnings for quarterly results, market for macro, research for default/follow-ups
- [ ] Task string for each agent includes thesis excerpt for context grounding
- [ ] Fallback to `[AgentTask(agent_type="research", task=query)]` if LLM call or JSON parse fails
- [ ] Typecheck passes

---

### US-006: ProjectAnalysisState TypedDict + graph skeleton
**Description:** As a developer, I need the LangGraph state definition and a compilable graph skeleton so the project graph has a verified foundation before agent nodes are added.

**Acceptance Criteria:**
- [ ] Create `agents/project_agent.py`
- [ ] `ProjectAnalysisState` TypedDict with fields: `query` (str), `project_id` (str), `context_block` (str, pre-populated by API handler), `routing_decision` (dict), `agent_results` (Annotated[List, operator.add]), `synthesis` (str), `memory_patch` (dict), `final_response` (str), `errors` (Annotated[List, operator.add]), `start_time` (float)
- [ ] Build compiled LangGraph graph with: `route` node (Node 1 — reads `routing_decision.agents`, uses `add_conditional_edges` to return list of selected `run_agent_*` node names), `sync_point` node (no-op aggregator — waits for all parallel agent nodes before proceeding), and stub no-op implementations for all 7 remaining nodes (`run_agent_dcf`, `run_agent_analyst`, `run_agent_earnings`, `run_agent_market`, `run_agent_research`, `synthesize`, `extract_memory_patch`) that pass state through unchanged
- [ ] Edges: `START → route`, `route --conditional--> {run_agent_*}`, all `run_agent_*` → `sync_point`, `sync_point → synthesize`, `synthesize → extract_memory_patch`, `extract_memory_patch → END`
- [ ] `graph.compile()` succeeds without error
- [ ] If `routing_decision` is empty or missing agents list, `route` falls back to `["run_agent_research"]`
- [ ] Typecheck passes

---

### US-006b: Agent runner nodes (dcf, analyst, earnings, market, research)
**Description:** As a developer, I need the 5 agent runner nodes implemented in the project graph so parallel agent execution actually runs and returns results.

**Acceptance Criteria:**
- [ ] In `agents/project_agent.py`, replace the 5 stub `run_agent_*` nodes with real implementations: `run_agent_dcf`, `run_agent_analyst`, `run_agent_earnings`, `run_agent_market`, `run_agent_research`
- [ ] Each node: finds its `AgentTask` from `state["routing_decision"].agents` by matching `agent_type`, prepends `state["context_block"]` to the task string, invokes the corresponding existing agent (DCFAnalysisAgent, EquityAnalystAgent, EarningsAgent, MarketAnalysisAgent, or research agent), appends `{"agent_type": str, "task": str, "output": str}` to `agent_results`
- [ ] If the agent raises an exception, the node appends to `errors` and appends a `{"agent_type": ..., "output": "Error: ..."}` entry to `agent_results` — it never re-raises
- [ ] `_emit_progress(event_type, data)` SSE helper emits a progress event at the start of each node (same pattern as `earnings_agent.py`)
- [ ] Typecheck passes

---

### US-006c: Synthesize + extract_memory_patch nodes + adapter
**Description:** As a developer, I need the synthesis and memory extraction nodes plus the graph adapter so the graph produces a final response and a memory patch that the API handler can use.

**Acceptance Criteria:**
- [ ] In `agents/project_agent.py`, replace stub `synthesize` node: 1 Sonnet LLM call that receives all `agent_results` outputs and the thesis from `context_block`, produces a cohesive response grounded in the thesis, writes to `state["synthesis"]` and `state["final_response"]`
- [ ] Replace stub `extract_memory_patch` node: 1 Haiku LLM call that reads `state["synthesis"]` and extracts a structured dict with keys `conclusions` (list of strings), `violated_assumptions` (list), `thesis_health` (dict with `status` and `rationale`), `open_questions` (list); writes to `state["memory_patch"]`
- [ ] If `agent_results` is empty (all agents failed), `synthesize` writes a graceful error message referencing the `errors` list
- [ ] `ProjectAnalysisGraph` class wrapping the compiled graph with a `run(query, project_id, context_block, routing_decision, callback_handler)` method
- [ ] `ProjectAnalysisGraphAdapter` exposing `.invoke({"input": query, "project_id": id, "context_block": str, "routing_decision": dict})` — same adapter pattern as `EarningsAgentExecutorAdapter` in `agents/earnings_agent.py`
- [ ] Typecheck passes

---

### US-007: Project CRUD REST endpoints
**Description:** As a developer, I need REST endpoints to create, read, update, and delete projects so the frontend can manage the project lifecycle.

**Acceptance Criteria:**
- [ ] Add to `backend/api_server.py`:
  - `POST /projects` — create project, call `initialize_memory_doc()`, return ProjectDetail
  - `GET /projects` — list active projects (id, title, thesis, status, created_at, updated_at, session_count, document_count)
  - `GET /projects/{project_id}` — full project detail including memory_doc
  - `PATCH /projects/{project_id}` — update title/thesis/config/status
  - `DELETE /projects/{project_id}` — set status='archived', delete Chroma collection
  - `GET /projects/{project_id}/memory` — return memory_doc string
  - `PATCH /projects/{project_id}/memory` — manual memory edit
  - `GET /projects/{project_id}/sessions` — list linked sessions
- [ ] `CreateProjectRequest` Pydantic model: title, thesis, tickers (optional list)
- [ ] Typecheck passes

---

### US-008: Document upload endpoint for projects
**Description:** As a developer, I need a document upload endpoint that extracts text, chunks it, embeds it in ChromaDB, and saves the record so uploaded files are semantically searchable within a project.

**Acceptance Criteria:**
- [ ] Add `POST /projects/{project_id}/documents` to `api_server.py`
- [ ] Reuse existing `extract_text_from_file()` function for PDF/DOCX/XLSX/CSV/PPTX extraction
- [ ] Call `chroma_client.add_document_chunks()` to embed and store chunks
- [ ] Call `generate_document_summary()` (Haiku LLM call) and append summary to memory_doc `Uploaded Document Summaries` section
- [ ] Save `ProjectDocument` record to SQLite with chunk_count and chroma_ids
- [ ] `GET /projects/{project_id}/documents` — list documents (no raw_text in response)
- [ ] `DELETE /projects/{project_id}/documents/{doc_id}` — delete record + delete chroma chunks
- [ ] Typecheck passes

---

### US-009: Inject project context into `/chat/stream`
**Description:** As a developer, I need the `/chat/stream` endpoint to detect when a session belongs to a project and route through ProjectAnalysisGraph with assembled context so project chats are grounded.

**Acceptance Criteria:**
- [ ] Extend `ChatMessage` (or create `ProjectChatMessage`) with optional `project_id: Optional[str]` field in `api_server.py`
- [ ] In `/chat/stream` handler: if `project_id` is present, (1) call `assemble_project_context(project_id, query, db, chroma_client)` to get `context_block`, (2) call `route_for_project(query, context_block, project.config)` to get `routing_decision`, (3) pass both `context_block` and `routing_decision` in the initial state dict when invoking `ProjectAnalysisGraph` — the graph receives both ready-made and does not re-assemble or re-route internally
- [ ] Modify `_persist_conversation()` to accept optional `project_id` and create `ProjectSession` link if set
- [ ] Pre-load `ProjectChromaClient` in FastAPI `on_startup` so embedding model downloads before first request
- [ ] Non-project sessions (`project_id=None`) are completely unaffected
- [ ] Typecheck passes

---

### US-010: Memory update background job
**Description:** As a developer, I need a non-blocking background task that patches the project memory document after each project response so memory compounds automatically across sessions.

**Acceptance Criteria:**
- [ ] After `ProjectAnalysisGraph` completes and `memory_patch` is populated, call `asyncio.create_task(update_project_memory(project_id, memory_patch, db))`
- [ ] `update_project_memory()` applies patch: prepend to `Accumulated Conclusions`, append to `Violated or Revised Assumptions`, replace `Thesis Health`, append to `Open Questions`
- [ ] After applying the patch, call `trim_memory_doc(memory_doc, max_conclusions=20, max_questions=10)` before writing back to SQLite, so the memory doc never grows unbounded
- [ ] Optimistic locking: load project row inside the task, apply patch + trim, write back with `updated_at` timestamp check; if the write affects 0 rows (concurrent update detected), re-read the latest memory_doc, re-apply the same patch + trim, and retry once before logging and dropping
- [ ] Task errors are logged (not raised) so a memory update failure never breaks the user response
- [ ] Typecheck passes

---

### US-011: Frontend TypeScript types for projects
**Description:** As a developer, I need TypeScript interfaces for projects, project documents, and extended chat requests so the frontend is fully type-safe.

**Acceptance Criteria:**
- [ ] Add to `frontend/src/types.ts`:
  - `ProjectSummary`: id, title, thesis, status, created_at, updated_at, session_count, document_count
  - `ProjectDetail extends ProjectSummary`: config (tickers, preferred_agents), memory_doc
  - `ProjectDocument`: id, project_id, filename, file_type, chunk_count, uploaded_at
- [ ] `ChatRequest` (or a new `ProjectChatRequest`) extended with optional `project_id?: string`
- [ ] Typecheck passes

---

### US-012: Frontend API client functions for projects
**Description:** As a developer, I need API client functions for all project endpoints so pages can fetch and mutate project data.

**Acceptance Criteria:**
- [ ] Add to `frontend/src/api.ts`:
  - `getProjects() → Promise<ProjectSummary[]>`
  - `getProject(id) → Promise<ProjectDetail>`
  - `createProject(title, thesis, tickers?) → Promise<ProjectDetail>`
  - `updateProject(id, patch) → Promise<ProjectDetail>`
  - `deleteProject(id) → Promise<void>`
  - `uploadProjectDocument(id, file) → Promise<ProjectDocument>`
  - `getProjectDocuments(id) → Promise<ProjectDocument[]>`
  - `deleteProjectDocument(projectId, docId) → Promise<void>`
  - `getProjectMemory(id) → Promise<string>`
  - `patchProjectMemory(id, memoryDoc) → Promise<void>`
  - `getProjectSessions(id) → Promise<SessionSummary[]>`
- [ ] `streamMessage()` passes `project_id` in request body when present
- [ ] Typecheck passes

---

### US-013: Sidebar — Projects section
**Description:** As a user, I want to see my projects in the sidebar so I can navigate to them quickly.

**Acceptance Criteria:**
- [ ] Add "Projects" NavLink (Folder icon) to navigation section in `Sidebar.tsx`, linking to `/projects`
- [ ] When sidebar is expanded: show a "Projects" section above "Recent Chats" listing up to 5 active projects
- [ ] Each project row shows title + thesis excerpt (first 60 chars) + click → navigate to `/projects/{id}`
- [ ] "View all projects →" link at bottom of section navigating to `/projects`
- [ ] Projects list loaded via `getProjects()` on mount + refreshed every 30s (same pattern as sessions)
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-014: App.tsx — add project routes
**Description:** As a developer, I need React Router routes for the projects list and workspace pages so the URLs resolve correctly.

**Acceptance Criteria:**
- [ ] Add `Route path="/projects"` → `ProjectsListPage` to `App.tsx`
- [ ] Add `Route path="/projects/:projectId"` → `ProjectWorkspace` to `App.tsx`
- [ ] Import both page components
- [ ] Existing routes (`/`, `/portfolio`, `/earnings`, `/library`) unchanged
- [ ] Typecheck passes

---

### US-015: ProjectsListPage — list and create projects
**Description:** As a user, I want to see all my investment projects and create new ones so I can manage my thesis workspaces.

**Acceptance Criteria:**
- [ ] Create `frontend/src/pages/ProjectsListPage.tsx`
- [ ] Fetches and displays active projects as cards: title, thesis excerpt (first 120 chars), session count, document count, last updated date
- [ ] "New Project" button opens an inline form with: title input, thesis textarea, optional tickers input (comma-separated)
- [ ] Submit calls `createProject()` and navigates to `/projects/{id}`
- [ ] Archive button on each card calls `deleteProject()` (soft archive) and removes from list
- [ ] Empty state: "No projects yet — create your first investment thesis" with New Project CTA
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-016: ProjectWorkspace — chat panel
**Description:** As a user, I want to chat with agents inside a project workspace so all my queries are grounded in my thesis and accumulated memory.

**Acceptance Criteria:**
- [ ] Create `frontend/src/pages/ProjectWorkspace.tsx`
- [ ] Loads project detail via `getProject(projectId)` from URL param
- [ ] Renders project title and thesis excerpt at top of page
- [ ] Left panel (2/3 width): reuses existing `<Chat>` component with `project_id` passed in every `streamMessage()` call
- [ ] Chat sessions created in this workspace are automatically linked to the project (handled server-side)
- [ ] Loads existing project sessions via `getProjectSessions()` and allows restoring them (same `?session=` URL param pattern)
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-017: ProjectWorkspace — memory and documents panel
**Description:** As a user, I want to see the living memory document and uploaded files in the project workspace so I can track how the thesis is evolving.

**Acceptance Criteria:**
- [ ] Right panel (1/3 width) in `ProjectWorkspace.tsx` with 3 tabs: "Memory", "Documents", "Sessions"
- [ ] **Memory tab**: renders `memory_doc` markdown (use existing `react-markdown` component); shows last-updated timestamp; "Edit" button toggles to textarea for manual edits (calls `patchProjectMemory()`)
- [ ] Memory tab auto-refreshes every 10s during an active session (polls `getProjectMemory()`)
- [ ] **Documents tab**: lists uploaded documents (filename, file type, chunk count, upload date); delete button per doc
- [ ] **Sessions tab**: lists `getProjectSessions()` result; click navigates to `/?session={id}`
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-018: ProjectWorkspace — document upload UI
**Description:** As a user, I want to upload research documents (PDFs, 10-Ks, news articles) to a project so they inform all future analyses.

**Acceptance Criteria:**
- [ ] In Documents tab: drag-drop upload zone accepts PDF, DOCX, XLSX, PPTX, CSV
- [ ] Reuse existing `FileUploadModal.tsx` patterns or replicate inline (whichever is simpler)
- [ ] On file drop/select: calls `uploadProjectDocument(projectId, file)` with loading state
- [ ] On success: document appears in list with chunk_count > 0
- [ ] On failure: error toast with message
- [ ] Max file size client-side check: 10MB
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-019: ProjectWorkspace — thesis health indicator
**Description:** As a user, I want to see the current thesis health status prominently in the workspace so I immediately know if the thesis is holding.

**Acceptance Criteria:**
- [ ] Parse `Thesis Health` section from `memory_doc` and display as a colored badge in the workspace header: STRONG (green), WEAKENING (yellow), CHALLENGED (orange), INVALIDATED (red)
- [ ] Badge shows status text + rationale on hover/tooltip
- [ ] Updates whenever memory panel refreshes (every 10s during active session)
- [ ] If memory_doc is empty or Thesis Health section not yet populated, show neutral "Not assessed" badge
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

### US-020: End-to-end integration test
**Description:** As a developer, I want to verify the full project feature flow works end-to-end so I can confirm all layers integrate correctly.

**Acceptance Criteria:**
- [ ] Can create a project via `POST /projects` and retrieve it via `GET /projects/{id}`
- [ ] Can upload a PDF to a project and verify `chunk_count > 0` in response
- [ ] Can send a chat message with `project_id` set and receive a streamed response that references the project thesis
- [ ] After the response, `GET /projects/{id}/memory` returns an updated `Accumulated Conclusions` section
- [ ] Frontend `/projects` page loads and displays created project
- [ ] Frontend `/projects/:id` workspace renders chat + memory panel
- [ ] Memory panel shows updated memory doc after a chat session
- [ ] Thesis health badge renders correctly

---

## Non-Goals

- No real-time price alerts or threshold notifications based on signals
- No automatic thesis invalidation (human-in-the-loop, AI suggests health status only)
- No sharing or multi-user collaboration on projects
- No project version history or memory rollback
- No fine-tuning or custom embeddings beyond the default all-MiniLM-L6-v2 model
- No mobile-specific layout for the project workspace

## Technical Considerations

- **Chroma cold-start**: Pre-load `DefaultEmbeddingFunction` at FastAPI `on_startup` (the model is ~90MB and downloads automatically on first use)
- **Async Chroma**: Wrap sync Chroma operations in `run_in_executor(None, fn)` since ChromaDB client is synchronous
- **Memory race condition**: Use optimistic locking (`updated_at` check) in `update_project_memory()` since concurrent sessions can both trigger background updates
- **`_persist_conversation()` modification**: Must accept optional `project_id` and create `ProjectSession` link — critical coupling point
- **Fan-out in LangGraph**: Pre-register all 6 agent nodes, use `add_conditional_edges` returning a list of selected node names from `routing_decision`
- **Context token budget**: memory_doc ≤800 tokens, chunks ≤5×400 tokens, thesis always verbatim — total ≤3500 tokens
- **Chroma version**: Pin `chromadb>=0.4.0,<0.6.0` to avoid breaking API changes
- **Chroma DB path**: Resolve relative to same directory as `finance_agent.db` using `os.path.dirname(os.path.abspath(__file__))`
- **Reuse existing patterns**: `extract_text_from_file()` for document text extraction, `route_agent_for_message()` pattern for Haiku routing call, `asyncio.create_task()` for background memory update, `EarningsAgentExecutorAdapter` pattern for LangGraph adapter
