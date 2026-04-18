# Phronesis Design System

> Financial Intelligence — white, teal, monospace.

## Brand

**Name:** Phronesis  
**Tagline:** Financial Intelligence  
**Monogram:** `P` in `#0F172A` navy square, 7px radius, 28×28px  

## Color Tokens

All colors are defined as CSS variables in `frontend/src/index.css`. Use tokens, not hardcoded hex.

| Token | Value | Use |
|---|---|---|
| `--teal-500` | `#10B981` | Primary accent — active states, CTAs, links, live indicators |
| `--teal-600` | `#059669` | Teal hover state |
| `--teal-50` | `#F0FDF4` | Teal tinted backgrounds (active nav, success states) |
| `--teal-100` | `#D1FAE5` | Teal borders |
| `--ink-900` | `#1A1A1A` | Primary body text, high-emphasis elements |
| `--navy-900` | `#0F172A` | Page titles, display headings, monogram |
| `--ink-700` | `#374151` | Secondary body text |
| `--ink-500` | `#6B7280` | Tertiary text, metadata |
| `--ink-400` | `#9CA3AF` | Placeholder text, disabled labels |
| `--ink-300` | `#ABABAB` | Muted text, timestamps |
| `--ink-200` | `#D1D5DB` | Borders (light) |
| `--ink-100` | `#E5E7EB` | Borders (default) |
| `--ink-50` | `#F9FAFB` | Subtle backgrounds |
| `--border-default` | `#EEEEEE` | Memo section dividers, panel borders |
| `--border-subtle` | `#F3F3F3` | Header/footer separators |
| `--surface-default` | `#FFFFFF` | Page background, card backgrounds |
| `--surface-subtle` | `#FAFAFA` | Input areas, checklist background |

### Semantic colors (not tokenized — use directly)

| Purpose | Value |
|---|---|
| BUY / bullish | `#15803D` (text), `#F0FDF4` (bg), `#BBF7D0` (border) |
| PASS / bearish | `#991B1B` (text), `#FEF2F2` (bg), `#FECACA` (border) |
| WATCH / neutral | `#92400E` (text), `#FFFBEB` (bg), `#FDE68A` (border) |
| Error | `#9F1239` (text), `#FFF1F2` (bg), `#FECDD3` (border) |

## Typography

Three fonts. Each has a defined role. Never mix roles.

| Font | Role | When to use |
|---|---|---|
| **IBM Plex Sans** | Body / UI | All body text, labels, nav items, descriptions, buttons, form inputs |
| **IBM Plex Mono** | Data / Terminal | Ticker symbols, amounts, percentages, dates, status labels, agent names, section labels, monogram |
| **Instrument Serif** | Display | Ticker name in memo header (32px), large display headings only |

**Not used:** Inter (removed from product; still present in legacy Earnings/Chat CSS — migrate in Phase 2).

### Type scale

| Class | Size | Weight | Font | Use |
|---|---|---|---|---|
| Page title | 24px | 700 | IBM Plex Sans | "Investment Memo" |
| Display ticker | 32px | 400 | Instrument Serif | AAPL in memo header |
| Section label | 9px | 700 | IBM Plex Mono | UPPERCASE section titles |
| Body | 13–15px | 400/500 | IBM Plex Sans | Paragraph text |
| Data label | 10–12px | 600–700 | IBM Plex Mono | Confidence %, dates, amounts |
| Caption | 10–11px | 400 | IBM Plex Sans | Subtitles, metadata |

## Layout

**Sidebar:** Fixed left, 60px collapsed / 240px expanded. Collapses to icon-only at ≤768px. Below 768px: hide sidebar entirely, show bottom nav bar.

**Main content:** `max-width: 820px`, centered with `margin: 0 auto`. Left margin of `80px` (collapsed sidebar width) on desktop.

**Mobile (≤768px):** Sidebar hidden. Bottom nav bar with 4 icon items (Memo, Earnings, Arena, Library). Main content `margin-left: 0`, full width with `16px` horizontal padding.

**Document width:** Memo and Library pages: 820px max. Chat page: 720px max.

## Components

### Navigation

4 primary nav items: Investment Memo, Earnings, Arena, Library.  
Active state: icon turns teal (`--teal-500`), label weight bumps to 600.  
Subtitle text always visible in expanded mode (`--ink-300`).

### Verdict Badge

`.verdict-badge` with `.buy` / `.watch` / `.pass` modifier classes.  
Font: IBM Plex Mono, 20px, 700 weight, 0.04em letter-spacing.

### Agent Card Row

Initials badge: 32×32px, 8px radius, color at 7% opacity (`${color}12`).  
Confidence bar: 2px height, `--ink-100` track, colored fill at 55% opacity.

### Memo Sections

Flat document flow — no card borders. Sections separated by `1px solid --border-default`.  
Section label: IBM Plex Mono, 9px, 700, uppercase, `--ink-300`, `0.1em` letter-spacing.

### Checklist

Section header: "Before you act" (IBM Plex Mono, 12px, 700, `--navy-900`).  
Subtitle: "Four questions that separate conviction from noise." (IBM Plex Sans, 12px, `--ink-400`).  
Background: `--surface-subtle`, dashed border `--ink-200`, 8px radius.

## Motion

| Animation | Duration | Curve |
|---|---|---|
| Fade in | 500ms | `cubic-bezier(0.16, 1, 0.3, 1)` |
| Slide from bottom | 600ms | `cubic-bezier(0.16, 1, 0.3, 1)` |
| Confidence bar fill | 600ms | `cubic-bezier(0.16, 1, 0.3, 1)` |
| Agent opacity (done) | 400ms | `ease` |
| Live dot pulse | 1.6s | `ease-in-out infinite` |

Respect `prefers-reduced-motion` — all animations disabled via media query in `index.css`.

## Voice

**Tone:** Direct, data-first, no fluff.  
**Labels:** Uppercase monospace for data labels, sentence case for body.  
**CTAs:** Uppercase monospace (`RUN ANALYSIS`, `SAVE DECISION`, `CANCEL`).  
**Status text:** Plain language, present tense ("Synthesizing investment memo…").
