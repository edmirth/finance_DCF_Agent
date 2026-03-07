# PRD: Data Visualization System — Inline Agent Charts

## Introduction

Agents currently produce rich financial data but output only markdown text. This feature adds Rogo/Hebba-style inline charts: charts appear at the exact point in the agent's narrative where the data is discussed (between paragraphs). Charts are auto-generated from tool outputs, light-themed, full-width, and persist across session reloads via the DB layer.

**Mechanism:** Tools append a `---CHART_DATA:id---` block to their output string. The LLM is instructed to place `{{CHART:id}}` placeholders inline. The streaming callback intercepts chart data blocks and emits `chart_data` SSE events. Message.tsx preprocesses placeholders into fenced code blocks that ReactMarkdown renders as `<AgentChart />` components.

---

## Goals

- Auto-generate charts from structured tool output (no manual trigger needed)
- Charts appear inline mid-narrative at semantically relevant positions
- Persist chart specs in DB so charts restore on session reload
- Light-themed design: `#F8FAFC` card, `#2563EB` primary, `#10B981` teal, Inter font
- Support 5 chart types: `bar_line`, `bar`, `line`, `grouped_bar`, `beat_miss_bar`
- PNG download via html2canvas
- Beat/miss EPS bars: green (#10B981) for beats, red (#EF4444) for misses

---

## Design System Reference

```
Card:       bg-[#F8FAFC] border border-[#E5E7EB] rounded-lg p-4 my-4
Title:      text-[#111827] text-base font-semibold font-inter
Grid:       horizontal only — stroke="#E5E7EB" strokeDasharray="3 3" vertical={false}
Chart H:    280px
Legend:     bottom-center, iconType="square" iconSize={10}
Palette:    #2563EB, #10B981, #F59E0B, #8B5CF6, #EC4899
Beat color: #10B981 (actual ≥ estimate), #EF4444 (actual < estimate)
```

---

## Inline Mechanism ({{CHART:id}} Placeholder System)

```
1. Tool._run() appends:
   ---CHART_DATA:quarterly_earnings_AAPL---
   {"id":"quarterly_earnings_AAPL","chart_type":"bar_line",...}
   ---END_CHART_DATA:quarterly_earnings_AAPL---
   [CHART_INSTRUCTION: Place {{CHART:quarterly_earnings_AAPL}} where you discuss revenue/EPS]

2. streaming.py on_tool_end():
   → Regex-extracts JSON from ---CHART_DATA:id--- block
   → Emits {type:"chart_data", id:"...", ...} SSE event

3. LLM follows [CHART_INSTRUCTION] and writes:
   "Revenue has grown significantly.
   {{CHART:quarterly_earnings_AAPL}}
   Breaking this down..."

4. Chat.tsx receives chart_data event:
   → message.chartsById["quarterly_earnings_AAPL"] = chartEvent

5. Message.tsx preprocessChartPlaceholders():
   {{CHART:id}} → ```chart:id\n```

6. ReactMarkdown renders code blocks with language="chart:id"
   → <AgentChart {...message.chartsById[id]} />
```

---

## Chart → Tool Mapping

### `get_quarterly_earnings` → `quarterly_earnings_{TICKER}` → `bar_line`
Data fields: `fiscal_period`, `revenue`, `net_income`, `weighted_average_shares`
Series: Revenue ($B) bar (left axis) + EPS ($) line (right axis)
Arrays: newest-first from API → reverse for chronological display

### `get_earnings_surprises` → `earnings_surprises_{TICKER}` → `beat_miss_bar`
Data fields (FMP): `date`, `epsActual`, `epsEstimated`
Series: gray estimate bar + conditional-colored actual bar (green=beat, red=miss)

### `get_analyst_estimates` → `analyst_estimates_{TICKER}` → `line`
Data fields (FMP quarterly): `date`, `epsAvg`, `epsHigh`, `epsLow`
Series: 3 lines — Consensus, High, Low

### `get_financial_metrics` (dcf_tools.py) → `financial_metrics_{TICKER}` → `bar_line`
Data fields: `historical_years[]`, `historical_revenue[]`, `historical_fcf[]`
Arrays: newest-first → reverse. Series: Revenue ($B) bar + FCF ($B) line

### `get_quick_data` (research_assistant_tools.py) → `quick_data_{TICKER}` → `bar`
Data fields: `historical_years[]`, `historical_revenue[]`
Arrays: newest-first → reverse. Series: Revenue ($B) bar only

---

## User Stories

### US-001: Add chart_specs column to DB (schema + migration)

**Description:** As a developer, I need to store chart specs in the messages table so charts restore on session reload.

**Files:**
- `backend/models.py` — add `chart_specs: Mapped[Optional[str]]` column to `DBMessage`
- `backend/database.py` — add safe `ALTER TABLE messages ADD COLUMN chart_specs TEXT` migration in `init_db()` (wrapped in try/except so it's idempotent)

**Acceptance Criteria:**
- [x] `DBMessage` has `chart_specs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)` field
- [x] `init_db()` runs `ALTER TABLE messages ADD COLUMN chart_specs TEXT` after `create_all`, wrapped in `try/except Exception: pass`
- [x] `from sqlalchemy import text` is imported in database.py (needed for raw SQL)
- [x] Typecheck passes

---

### US-002: Add chart blocks to earnings_tools.py (4 tools)

**Description:** As a developer, I need 3 earnings tools to append structured `---CHART_DATA---` blocks so the streaming callback can extract chart specs.

**Files:** `tools/earnings_tools.py`

**Key changes:**

1. Add `import json` at the top (after existing imports).

2. **`GetQuarterlyEarningsTool._run()`** — After calling `self._format_quarterly_earnings(quarterly_data, ticker, quarters)`, append chart block. Build chart data from `income_stmts = quarterly_data.get("income_statements", [])`. Reverse list for chronological order. EPS = `net_income / weighted_average_shares` (null-safe: `if shares else 0`). Wrap in `try/except Exception: pass`.

3. **`GetEarningsSurprisesTool._fetch_from_fmp()`** — After building `historical` list and calling `_format_earnings_surprises_from_calendar(historical[:quarters], ticker)`, append chart block using `historical` data. Fields: `date` → period, `epsActual`, `epsEstimated`. beat = `epsActual >= epsEstimated`. Wrap in `try/except Exception: pass`.

4. **`GetAnalystEstimatesTool._format_fmp_estimates()`** — At the end before returning, append chart block from `quarterly` list. Fields: `date`, `epsAvg` (or `estimatedEpsAvg`), `epsHigh`, `epsLow`. Wrap in `try/except Exception: pass`.

**Chart ID format:** `quarterly_earnings_{ticker.upper()}`, `earnings_surprises_{ticker.upper()}`, `analyst_estimates_{ticker.upper()}`

**Chart block format:**
```
\n---CHART_DATA:{chart_id}---\n{json_string}\n---END_CHART_DATA:{chart_id}---
\n[CHART_INSTRUCTION: Place {{CHART:{chart_id}}} on its own line where you discuss X. Do NOT reproduce the CHART_DATA block.]
```

**Chart JSON for quarterly_earnings:**
```json
{
  "id": "quarterly_earnings_AAPL",
  "chart_type": "bar_line",
  "title": "AAPL Quarterly Revenue & EPS",
  "data": [{"period": "Q1 2024", "revenue_b": 119.58, "eps": 2.18}, ...],
  "series": [
    {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
    {"key": "eps", "label": "EPS ($)", "type": "line", "color": "#10B981", "yAxis": "right"}
  ],
  "y_format": "currency_b",
  "y_right_format": "currency"
}
```

**Chart JSON for earnings_surprises:**
```json
{
  "id": "earnings_surprises_AAPL",
  "chart_type": "beat_miss_bar",
  "title": "AAPL EPS: Actual vs. Estimate",
  "data": [{"period": "2024-01-01", "eps_actual": 2.18, "eps_estimate": 2.10, "beat": true}, ...],
  "series": [
    {"key": "eps_estimate", "label": "Estimate", "type": "bar", "color": "#E5E7EB", "yAxis": "left"},
    {"key": "eps_actual", "label": "Actual", "type": "bar", "color": "#2563EB", "yAxis": "left",
     "colorByField": "beat", "colorIfTrue": "#10B981", "colorIfFalse": "#EF4444"}
  ],
  "y_format": "currency"
}
```

**Chart JSON for analyst_estimates:**
```json
{
  "id": "analyst_estimates_AAPL",
  "chart_type": "line",
  "title": "AAPL Forward EPS Estimates",
  "data": [{"period": "2025-03-31", "eps_avg": 1.62, "eps_high": 1.72, "eps_low": 1.52}, ...],
  "series": [
    {"key": "eps_avg", "label": "Consensus EPS", "type": "line", "color": "#2563EB"},
    {"key": "eps_high", "label": "High Est.", "type": "line", "color": "#10B981"},
    {"key": "eps_low", "label": "Low Est.", "type": "line", "color": "#F59E0B"}
  ],
  "y_format": "currency"
}
```

**Acceptance Criteria:**
- [x] `import json` added at top of file
- [x] `GetQuarterlyEarningsTool._run()` appends chart block with `bar_line` chart data when income_stmts available
- [x] EPS calculation is null-safe: `eps = round(net_income / shares, 2) if shares else 0`
- [x] `GetEarningsSurprisesTool._fetch_from_fmp()` appends `beat_miss_bar` chart block after formatting
- [x] `GetAnalystEstimatesTool._format_fmp_estimates()` appends `line` chart block before returning
- [x] All chart block construction wrapped in `try/except Exception: pass` so failures are silent
- [x] Each block uses exact format: `\n---CHART_DATA:{id}---\n{json}\n---END_CHART_DATA:{id}---\n[CHART_INSTRUCTION: ...]`
- [x] Typecheck passes

---

### US-003: Add chart blocks to dcf_tools.py and research_assistant_tools.py

**Description:** As a developer, I need 2 more tools to emit chart blocks for revenue history charts.

**Files:** `tools/dcf_tools.py`, `tools/research_assistant_tools.py`

**Changes:**

**`tools/dcf_tools.py` — `GetFinancialMetricsTool._run()`**

After building `result` (the final return string), before `return result`:
- Extract `years = list(reversed(metrics.get('historical_years', [])))`, `rev = list(reversed(metrics.get('historical_revenue', [])))`, `fcf = list(reversed(metrics.get('historical_fcf', [])))`
- Build `bar_line` chart data pairing year+revenue+fcf (skip items where revenue or fcf is falsy)
- Chart ID: `financial_metrics_{ticker.upper()}`
- If chart data is non-empty, append chart block to `result`
- Wrap in `try/except Exception: pass`
- `import json` is already present at top of dcf_tools.py ✓

**Chart JSON for financial_metrics:**
```json
{
  "id": "financial_metrics_AAPL",
  "chart_type": "bar_line",
  "title": "AAPL Annual Revenue & FCF",
  "data": [{"period": "2020", "revenue_b": 274.52, "fcf_b": 73.37}, ...],
  "series": [
    {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
    {"key": "fcf_b", "label": "FCF ($B)", "type": "line", "color": "#10B981", "yAxis": "right"}
  ],
  "y_format": "currency_b",
  "y_right_format": "currency_b"
}
```

**`tools/research_assistant_tools.py` — `QuickFinancialDataTool._run()`**

After building `result.strip()` (just before `return result.strip()`):
- Extract `years = list(reversed(key_metrics.get('historical_years', [])))`, `rev = list(reversed(key_metrics.get('historical_revenue', [])))`
- Build `bar` chart data (only when `historical_revenue` and `historical_years` are available)
- Chart ID: `quick_data_{ticker.upper()}`
- If chart data is non-empty, append chart block to result
- Wrap in `try/except Exception: pass`
- Add `import json` at top of file if not already present

**Chart JSON for quick_data:**
```json
{
  "id": "quick_data_AAPL",
  "chart_type": "bar",
  "title": "AAPL Revenue History ($B)",
  "data": [{"period": "2020", "revenue_b": 274.52}, ...],
  "series": [
    {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB"}
  ],
  "y_format": "currency_b"
}
```

**Acceptance Criteria:**
- [x] `GetFinancialMetricsTool._run()` appends `bar_line` chart block to result string (before return)
- [x] Arrays are reversed from newest-first to oldest-first before building chart data
- [x] Data items with falsy revenue or fcf are skipped
- [x] `QuickFinancialDataTool._run()` appends `bar` chart block when historical data available
- [x] `import json` present at top of research_assistant_tools.py
- [x] All chart block construction wrapped in `try/except Exception: pass`
- [x] Typecheck passes

---

### US-004: Update streaming.py to extract chart_data SSE events

**Description:** As a developer, I need the streaming callback to intercept `---CHART_DATA---` blocks from tool outputs and emit them as structured SSE events.

**File:** `backend/callbacks/streaming.py`

**Change:** In `on_tool_end()`, add chart extraction at the very beginning (before extracting sources):

```python
async def on_tool_end(self, output: str, **kwargs: Any) -> None:
    """Called when tool execution ends"""
    import json as _json
    import re as _re
    output = self._ensure_str(output)

    # Extract chart data blocks and emit as chart_data events
    _CHART_RE = _re.compile(
        r'---CHART_DATA:([^-\n]+)---\n(.*?)\n---END_CHART_DATA:[^-\n]+---',
        _re.DOTALL
    )
    for match in _CHART_RE.finditer(output):
        try:
            chart_event = _json.loads(match.group(2).strip())
            chart_event["type"] = "chart_data"
            await self.queue.put(chart_event)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"chart_data parse error: {e}")

    # Extract sources from output (existing code follows)
    sources = self._extract_sources_from_output(output)
    ...
```

**Acceptance Criteria:**
- [x] `on_tool_end()` uses regex `r'---CHART_DATA:([^-\n]+)---\n(.*?)\n---END_CHART_DATA:[^-\n]+---'` with `re.DOTALL`
- [x] Each matched JSON blob is parsed and emitted to queue with `type: "chart_data"` field added
- [x] Parse errors are caught silently (logged as warning, not raised)
- [x] Existing source extraction and `tool_result` event emission unchanged
- [x] Typecheck passes

---

### US-005: Add chart placeholder instructions to agent prompts (finance_qa, dcf, equity_analyst)

**Description:** As a developer, I need 3 agent prompts to instruct the LLM to use `{{CHART:id}}` placeholders inline in its response.

**Files:**
- `agents/finance_qa_agent.py`
- `agents/dcf_agent.py`
- `agents/equity_analyst_agent.py`

**`agents/finance_qa_agent.py`** — In `_create_agent()`, find where `intro` string is built. After the existing content (after the SEC FILING WORKFLOW section or at the end of the system message), append:

```python
chart_instructions = """
**CHART PLACEHOLDERS:**
Some tool outputs include [CHART_INSTRUCTION: Place {{CHART:id}} ...].
Follow the instruction exactly: place {{CHART:chart_id}} on its own line at the exact point where the chart is relevant.
Do NOT reproduce ---CHART_DATA--- blocks or [CHART_INSTRUCTION] text in your response. Only use the {{CHART:id}} placeholder.
"""
```

Then include `chart_instructions` when building the system prompt.

**`agents/dcf_agent.py`** — In `_create_agent()`, find the `template` string. Add the following instruction block (anywhere in the template, ideally near the top after the PHASE 1 description):

```
CHART PLACEHOLDERS: When a tool output includes [CHART_INSTRUCTION: Place {{CHART:id}} ...], follow the instruction.
Place {{CHART:chart_id}} on its own line at the relevant point in your response.
Do NOT reproduce ---CHART_DATA--- blocks in your response.
```

Note: In Python f-strings with `{tools}` style template variables, `{{` and `}}` are literal braces. Since the DCF agent template uses `{tools}` and `{tool_names}` etc., the `{{CHART:id}}` in the instruction text must be written as `{{{{CHART:id}}}}` inside an f-string, OR the instruction string must be outside the f-string and concatenated, OR use a raw string for that section. Inspect the existing template structure to determine the right approach.

**`agents/equity_analyst_agent.py`** — In `_create_agent()`, find the `system_message` string. After the existing DATA-GATHERING WORKFLOW section, append:

```
**CHART PLACEHOLDERS:**
When a tool output includes [CHART_INSTRUCTION: Place {{CHART:id}} ...], follow the instruction.
Place {{CHART:chart_id}} on its own line at the exact point in the report where the chart data is relevant.
Do NOT reproduce ---CHART_DATA--- blocks or [CHART_INSTRUCTION] text in your output.
```

Again, watch for f-string brace escaping if the system_message uses an f-string.

**Acceptance Criteria:**
- [x] `finance_qa_agent.py` system prompt includes chart placeholder instructions
- [x] `dcf_agent.py` template includes chart placeholder instructions with correct brace escaping
- [x] `equity_analyst_agent.py` system_message includes chart placeholder instructions with correct brace escaping
- [x] No existing prompt content removed or broken
- [x] Typecheck passes

---

### US-006: Update earnings_agent.py with hardcoded chart placeholders in LLM prompts

**Description:** As a developer, I need the earnings agent's LangGraph LLM prompts to include hardcoded chart placeholders, since tool outputs are not directly visible to these nodes.

**File:** `agents/earnings_agent.py`

**IMPORTANT:** The earnings agent uses LangGraph. The `comprehensive_analysis` (line ~576) and `develop_thesis` (line ~690) nodes receive aggregated state — they do NOT see raw tool output strings. Chart placeholders must be hardcoded using the ticker from state.

**In `comprehensive_analysis` node** (~line 576), inside the `prompt` f-string, add after the "Be specific with numbers" line:

```python
f"""
CHART PLACEHOLDERS — include these on their own line where relevant:
- Where you discuss quarterly revenue/EPS trends: {{CHART:quarterly_earnings_{state['ticker']}}}
- Where you discuss earnings surprises (beats/misses): {{CHART:earnings_surprises_{state['ticker']}}}
- Where you discuss analyst consensus estimates: {{CHART:analyst_estimates_{state['ticker']}}}
Do NOT reproduce any ---CHART_DATA--- blocks.
"""
```

Note: since the node's `prompt` is already an f-string, `{state['ticker']}` is already a valid f-string expression. `{{CHART:...}}` becomes literal `{CHART:...}` in the rendered string (correct, since it's passed to an LLM, not another Python f-string).

**Do NOT modify** `develop_thesis` node — `ComparePeerEarningsTool` is excluded from chart generation (see Non-Goals), so there is no `chart_data` event for peer comparison. Adding a placeholder here would produce a silently-invisible element.

**Do NOT modify** `generate_report` node (it's a template string, not an LLM call).

**Acceptance Criteria:**
- [x] `comprehensive_analysis` prompt includes 3 chart placeholder instructions: `quarterly_earnings_`, `earnings_surprises_`, `analyst_estimates_`
- [x] `develop_thesis` node is NOT modified (no chart data source exists for peer comparison)
- [x] All placeholders use `{{CHART:..._{state['ticker']}}}` pattern (double-brace for f-string literal)
- [x] `generate_report` node is NOT modified
- [x] Typecheck passes

---

### US-007: Update api_server.py to collect, persist, and return chart specs

**Description:** As a developer, I need the API server to collect chart_data events during streaming, persist them alongside messages, and return them in the sessions endpoint.

**File:** `backend/api_server.py`

**Changes:**

**A) In `stream_agent_response()`** — Add `collected_charts: dict = {}` after `collected_thinking: list = []`. In the event loop, handle `chart_data` events:

```python
elif event["type"] == "chart_data":
    chart_id = event.get("id")
    if chart_id:
        collected_charts[chart_id] = event
    # Also stream to frontend so live messages get charts
    yield f"data: {json.dumps(event)}\n\n"
```

Also ensure `chart_data` events are NOT added to `collected_thinking`.

**B) In the `_persist_conversation()` call** — Add `chart_specs=collected_charts` parameter.

**C) Update `_persist_conversation()` signature** — Add `chart_specs: dict = None` parameter. When saving the assistant `DBMessage`, add:
```python
chart_specs=json.dumps(chart_specs) if chart_specs else None,
```

**D) In `get_session()` endpoint** — Add `chart_specs` to the message serialization dict:
```python
"chart_specs": m.chart_specs,  # raw JSON string or None
```

**Acceptance Criteria:**
- [x] `collected_charts: dict = {}` initialized in `stream_agent_response()`
- [x] `chart_data` events are captured into `collected_charts[event["id"]] = event` AND streamed to frontend via SSE
- [x] `chart_data` events are NOT added to `collected_thinking`
- [x] `_persist_conversation()` receives `chart_specs` parameter
- [x] Assistant `DBMessage` is saved with `chart_specs=json.dumps(chart_specs) if chart_specs else None`
- [x] `GET /sessions/{id}` returns `"chart_specs": m.chart_specs` for each message
- [x] Typecheck passes

---

### US-008: Create frontend/src/components/AgentChart.tsx (new file)

**Description:** As a user, I want to see beautiful inline charts rendered from agent data at the relevant point in the response.

**File:** `frontend/src/components/AgentChart.tsx` (NEW)

**Dependencies:** Install if not already present: `recharts`, `html2canvas`. Check `package.json` first — add to devDependencies/dependencies if missing.

**Component requirements:**

```typescript
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
         Legend, ResponsiveContainer, Cell } from 'recharts';
import html2canvas from 'html2canvas';
import { useRef } from 'react';
import { Download } from 'lucide-react';

interface ChartSeriesConfig {
  key: string;
  label: string;
  type: 'bar' | 'line';
  color: string;
  yAxis?: 'left' | 'right';
  colorByField?: string;   // for beat_miss_bar: boolean field in data
  colorIfTrue?: string;    // color when field is true (beat)
  colorIfFalse?: string;   // color when field is false (miss)
}

interface AgentChartProps {
  id: string;
  chart_type: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar';
  title: string;
  data: Array<Record<string, string | number | boolean>>;
  series: ChartSeriesConfig[];
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
}

const FORMAT: Record<string, (v: number) => string> = {
  currency_b: (v) => `$${v.toFixed(1)}B`,
  currency_t: (v) => `$${v.toFixed(1)}T`,
  currency:   (v) => `$${v.toFixed(2)}`,
  percent:    (v) => `${v.toFixed(1)}%`,
  number:     (v) => v.toLocaleString(),
};
```

**Card style:**
```
<div className="bg-[#F8FAFC] border border-[#E5E7EB] rounded-lg p-4 my-4 w-full">
  <div className="flex justify-between items-start mb-3">
    <span className="text-[#111827] text-base font-semibold font-inter">{title}</span>
    <button onClick={handleDownload} className="...download button...">
      <Download className="w-4 h-4" />
    </button>
  </div>
  <ResponsiveContainer width="100%" height={280}>
    <ComposedChart data={data}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
      <XAxis dataKey="period" tick={{ fill: "#6B7280", fontSize: 12, fontFamily: "Inter" }} />
      <YAxis tick={{ fill: "#6B7280", fontSize: 12, fontFamily: "Inter" }} tickFormatter={leftFormatter} />
      {hasRightAxis && <YAxis yAxisId="right" orientation="right" tickFormatter={rightFormatter} />}
      <Tooltip contentStyle={{ ... light style ... }} />
      <Legend iconType="square" iconSize={10} wrapperStyle={{ fontFamily: "Inter", fontSize: 12 }} />
      {series.map(s => s.type === 'bar' ? renderBar(s) : renderLine(s))}
    </ComposedChart>
  </ResponsiveContainer>
</div>
```

**For `beat_miss_bar` type:** Render bars with `<Cell>` for conditional coloring:
```tsx
<Bar key={s.key} dataKey={s.key} name={s.label} yAxisId="left">
  {data.map((entry, i) => (
    <Cell key={i} fill={
      s.colorByField
        ? entry[s.colorByField] ? s.colorIfTrue : s.colorIfFalse
        : s.color
    } />
  ))}
</Bar>
```

**PNG Download:**
```typescript
const chartRef = useRef<HTMLDivElement>(null);
const handleDownload = async () => {
  if (!chartRef.current) return;
  const canvas = await html2canvas(chartRef.current, { scale: 2 });
  const link = document.createElement('a');
  link.download = `${title.replace(/\s+/g, '_')}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
};
```

**Acceptance Criteria:**
- [x] `recharts` and `html2canvas` are installed (in package.json) — add if missing
- [x] AgentChart.tsx created with correct props interface
- [x] Card uses `bg-[#F8FAFC] border border-[#E5E7EB] rounded-lg p-4 my-4`
- [x] Grid: horizontal only (`vertical={false}`) with `stroke="#E5E7EB"`
- [x] Axis tick color `#6B7280`, font Inter, size 12
- [x] `beat_miss_bar` type renders conditional Cell colors using `colorByField`/`colorIfTrue`/`colorIfFalse`
- [x] PNG download button top-right, uses html2canvas at scale=2
- [x] `y_format` and `y_right_format` drive axis tick formatters from FORMAT map
- [x] Right Y-axis rendered when any series has `yAxis: "right"`
- [x] Component exported as named export `AgentChart`
- [x] Typecheck passes
- [ ] Verify changes work in browser

---

### US-009: Update frontend/src/types.ts with chart types

**Description:** As a developer, I need TypeScript interfaces for chart data events and the chartsById field on Message.

**File:** `frontend/src/types.ts`

**Add to StreamEvent type union:** `| "chart_data"`

**Add new interfaces:**

```typescript
export interface ChartSeriesConfig {
  key: string;
  label: string;
  type: 'bar' | 'line';
  color: string;
  yAxis?: 'left' | 'right';
  colorByField?: string;
  colorIfTrue?: string;
  colorIfFalse?: string;
}

export interface ChartDataEvent {
  type: 'chart_data';
  id: string;
  chart_type: 'bar_line' | 'bar' | 'line' | 'multi_line' | 'grouped_bar' | 'beat_miss_bar';
  ticker?: string;
  title: string;
  data: Array<Record<string, string | number | boolean>>;
  series: ChartSeriesConfig[];
  y_format?: 'number' | 'currency' | 'currency_b' | 'currency_t' | 'percent';
  y_right_format?: string;
}
```

**Update `Message` interface** — add `chartsById` field:
```typescript
chartsById?: Record<string, ChartDataEvent>;
```

**Update `SessionMessage` interface** — add `chart_specs` field:
```typescript
chart_specs?: string | null;  // raw JSON string from DB
```

**Acceptance Criteria:**
- [x] `"chart_data"` added to `StreamEvent` type union
- [x] `ChartSeriesConfig` interface exported
- [x] `ChartDataEvent` interface exported with all fields
- [x] `Message` interface has `chartsById?: Record<string, ChartDataEvent>`
- [x] `SessionMessage` interface has `chart_specs?: string | null`
- [x] Typecheck passes

---

### US-010: Update Chat.tsx to handle chart_data events (live + session reload)

**Description:** As a user, I want charts to appear in real-time during streaming and to be restored when I reload a session.

**File:** `frontend/src/components/Chat.tsx`

**Changes:**

**A) Import `ChartDataEvent` from types.ts**

**B) Handle `chart_data` event in the stream callback** (inside `streamMessage()` callback, after the `follow_ups` handler block):

```typescript
} else if (event.type === 'chart_data') {
  const chartEvent = event as unknown as ChartDataEvent;
  if (chartEvent.id) {
    setMessages(prev => prev.map(msg =>
      msg.id === assistantMessageId
        ? { ...msg, chartsById: { ...(msg.chartsById ?? {}), [chartEvent.id]: chartEvent } }
        : msg
    ));
  }
}
```

**C) Session reload — parse chart_specs when restoring messages from `initialMessages` prop.** Find where `initialMessages` is used to set messages state. The `initialMessages` arrive from the parent (ChatPage.tsx likely). The chart_specs on each message is a JSON string from the backend. In the `useEffect` that restores `initialMessages`, parse chart_specs:

Find this pattern (in the `useEffect` that responds to `initialMessages`):
```typescript
useEffect(() => {
  if (initialMessages && initialMessages.length > 0) {
    setMessages(initialMessages);
  }
}, [initialMessages]);
```

Change to:
```typescript
useEffect(() => {
  if (initialMessages && initialMessages.length > 0) {
    const withCharts = initialMessages.map(m => ({
      ...m,
      chartsById: (m as any).chart_specs
        ? JSON.parse((m as any).chart_specs)
        : m.chartsById,
    }));
    setMessages(withCharts);
  }
}, [initialMessages]);
```

**Acceptance Criteria:**
- [x] `chart_data` events are handled in the stream callback and update `chartsById` on the assistant message
- [x] Session reload useEffect parses `chart_specs` JSON string into `chartsById` on each message
- [x] `ChartDataEvent` type imported from `../types`
- [x] Existing event handling (thought, tool, content, etc.) unchanged
- [x] Typecheck passes

---

### US-011: Update Message.tsx for chart rendering (cleanContent + placeholder + renderer)

**Description:** As a user, I want chart placeholders in the agent response to render as actual inline charts, and chart system artifacts to be stripped from visible text.

**File:** `frontend/src/components/Message.tsx`

**Changes:**

**A) Import `AgentChart`:**
```typescript
import { AgentChart } from './AgentChart';
```

**B) Add safety strips to `cleanContent()`** — after the existing `.replace(...)` chain, before `.trim()`:
```typescript
// Strip chart system artifacts if LLM accidentally echoes them
.replace(/\[CHART_INSTRUCTION:[^\]]*\]/g, '')
.replace(/---CHART_DATA:[^-\n]*---[\s\S]*?---END_CHART_DATA:[^-\n]*---/g, '')
```

**C) Add `preprocessChartPlaceholders()` function** (module-level, outside component):
```typescript
function preprocessChartPlaceholders(content: string): string {
  return content.replace(
    /\{\{CHART:([^}]+)\}\}/g,
    (_, id) => `\`\`\`chart:${id.trim()}\n\`\`\``
  );
}
```

**D) Apply preprocessing** — after `const displayContent = ...`, add:
```typescript
const processedContent = isUser ? displayContent : preprocessChartPlaceholders(displayContent);
```

Replace the `displayContent` passed to `ReactMarkdown` with `processedContent`.

**E) Update the `ReactMarkdown` components prop** — `financialTableComponents` (from FinancialTable.tsx) defines only `table`, `thead`, `tbody`, `tr`, `th`, `td`. It has **no `code` renderer**, so there is no conflict. Spread it and add `code` alongside:

```typescript
components={{
  ...financialTableComponents,
  code: ({ node, inline, className, children, ...props }: any) => {
    const match = /^chart:(.+)$/.exec((className ?? '').replace('language-', ''));
    if (match && !inline) {
      const chartId = match[1];
      const chartData = message.chartsById?.[chartId];
      if (chartData) return <AgentChart {...chartData} />;
      return null;  // placeholder not yet loaded — render nothing
    }
    // Default code block rendering
    return <code className={className} {...props}>{children}</code>;
  }
}}

**Acceptance Criteria:**
- [ ] `AgentChart` imported from `./AgentChart`
- [ ] `cleanContent()` strips `[CHART_INSTRUCTION:...]` patterns
- [ ] `cleanContent()` strips `---CHART_DATA:...---END_CHART_DATA:...---` blocks
- [ ] `preprocessChartPlaceholders()` converts `{{CHART:id}}` → ` ```chart:id\n``` `
- [ ] `processedContent` is passed to `ReactMarkdown` instead of raw `displayContent`
- [ ] ReactMarkdown `code` component renders `<AgentChart />` for `language-chart:*` code blocks
- [ ] Unknown chart IDs (chartsById missing) return `null` (not an error)
- [ ] Existing code/inline code rendering still works for non-chart code blocks
- [ ] Typecheck passes
- [ ] Verify changes work in browser

---

## Non-Goals

- No chart type for `ComparePeerEarningsTool` (Tavily returns unstructured text — no chart data)
- No chart for the `analyze_industry`, `analyze_competitors`, `analyze_moat` tools
- No chart for `perform_dcf_analysis` (results are narrative, not tabular time-series)
- No chart editing or configuration by users
- No chart type switching UI
- No animated transitions
- No mobile-optimized chart sizing (full-width responsive is sufficient)
- No server-side chart rendering

---

## Technical Considerations

- **recharts** and **html2canvas** must be in `frontend/package.json` (check before creating US-008)
- **Double-brace escaping in f-strings:** `{{CHART:id}}` in an f-string renders as `{CHART:id}` — correct since it's passed to LLM. But `{{{{CHART:id}}}}` is needed if you're building a string that contains `{{CHART:id}}` as text (for templates-of-templates). Study each agent's string construction carefully.
- **DB migration is idempotent:** `ALTER TABLE ... ADD COLUMN` wrapped in `try/except` safely no-ops if column exists
- **chart_data events must be streamed to frontend:** They cannot only go to `collected_charts` — they must also be yielded as SSE events so live messages get charts
- **beat_miss_bar type:** Uses Recharts `<Bar>` with `<Cell>` children for per-bar color. The estimate bar (gray `#E5E7EB`) and actual bar (`colorByField`) stack side-by-side, not stacked
- **existing ReactMarkdown code renderer:** Check Message.tsx for existing `code` component before adding — merge, don't replace
- **FinancialTable.tsx:** `financialTableComponents` is already imported in Message.tsx — it also provides a `code` renderer. Check for conflicts before adding chart code renderer

---

## Dependency Order

```
US-001 (DB schema)
  → US-007 (api_server uses new DB column)
US-002 (earnings_tools chart blocks)
  → US-004 (streaming extracts them)
  → US-006 (earnings_agent prompt references chart IDs)
US-003 (dcf+research_assistant chart blocks)
  → US-004 (streaming extracts them)
  → US-005 (agent prompts reference chart IDs)
US-009 (types)
  → US-008 (AgentChart uses types)
  → US-010 (Chat.tsx uses types)
  → US-011 (Message.tsx uses AgentChart)
```

**Recommended implementation order:** US-001 → US-002 → US-003 → US-004 → US-005 → US-006 → US-007 → US-009 → US-008 → US-010 → US-011
