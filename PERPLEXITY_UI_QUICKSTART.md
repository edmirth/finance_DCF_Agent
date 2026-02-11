# Perplexity-Style UI - Quick Start Guide

## What Changed?

The Earnings Analyst now uses a **clean, document-style interface** instead of colorful chat bubbles.

### Before → After

**Before**: 🔵 Colored cards with shadows and gradients
**After**: 📄 Clean white document with professional typography

---

## Start Using It

### 1. Start the Application

```bash
cd /Users/edmir/finance_dcf_agent
./start_web.sh
```

### 2. Open Browser

Navigate to: `http://localhost:3000/earnings`

### 3. Analyze a Company

- Enter ticker: `AAPL`
- Click "Analyze Earnings"
- Wait ~30-60 seconds

---

## What You'll See

### Metadata Bar (Top)
```
⏱ Worked for 45s                📊 📰 📈 7 sources
──────────────────────────────────────────────────
```

### Document Title
```
Apple Inc. (AAPL) Earnings Analysis
═══════════════════════════════════════════════
```

### Clean Sections
```
Executive Summary

Apple reported strong Q4 results[1], with revenue
growing 6% YoY to $89.5B. The company provided
cautious Q1 guidance citing macro headwinds[2].

Quarterly Performance

| Quarter | Revenue | EPS   | Growth |
|---------|---------|-------|--------|
| Q4 2025 | $89.5B  | $1.64 | +6.0%  |
| Q3 2025 | $81.8B  | $1.46 | +4.8%  |
```

### Citations (Bottom)
```
Sources
[1] Financial Datasets - Q4 2025 Earnings Data
[2] Earnings Call Transcript - Management Guidance
```

---

## Key Features

### ✅ What's New

- **Metadata bar**: Shows analysis time and source count
- **Citations**: Small numbered badges link to sources
- **Clean tables**: Professional grid formatting
- **Linear flow**: All content visible, no collapsing
- **Document feel**: Looks like analyst research

### ❌ What's Gone

- Colored background cards
- Heavy shadows and gradients
- Collapsible sections
- Glass morphism effects
- Multiple accent colors

---

## Design Highlights

### Colors
- **Background**: Pure white
- **Text**: Grayscale (black → gray)
- **Accent**: Teal (citations only)
- **Borders**: Subtle gray

### Typography
- **Title**: Georgia serif, 36px
- **Headings**: IBM Plex Sans, 24px
- **Body**: IBM Plex Sans, 16px
- **Tables**: IBM Plex Mono

### Layout
- **Max width**: 896px (centered)
- **Spacing**: Generous margins
- **Borders**: Thin, subtle
- **Corners**: Minimal rounding

---

## Components

### New Files
```
frontend/src/components/
  ├── CitationBadge.tsx        # Inline citations
  ├── MetadataBar.tsx          # Time + sources
  ├── DocumentSection.tsx      # Section rendering
  └── EarningsDocumentView.tsx # Main component

frontend/src/utils/
  └── citationParser.ts        # Citation extraction
```

### Modified Files
```
frontend/src/
  ├── types.ts              # Added Citation type
  ├── index.css             # Document styles
  └── pages/EarningsPage.tsx # Uses new component
```

---

## Troubleshooting

### Build Errors
```bash
cd frontend
npm run build
```
Should complete without errors.

### Styles Not Appearing
1. Clear browser cache (Ctrl+Shift+R)
2. Check browser console (F12) for errors
3. Verify backend is running

### Backend Issues
```bash
cd backend
python api_server.py
```
Should start on port 8000.

---

## Quick Reference

### Run Development Server
```bash
cd frontend && npm run dev
```

### Build Production
```bash
cd frontend && npm run build
```

### Check Backend API
```
http://localhost:8000/docs
```

### Access Earnings Page
```
http://localhost:3000/earnings
```

---

## Documentation

- **Implementation details**: `PERPLEXITY_UI_IMPLEMENTATION.md`
- **Visual comparison**: `UI_TRANSFORMATION_SUMMARY.md`
- **Verification steps**: `VERIFICATION_STEPS.md`
- **Main docs**: `CLAUDE.md`

---

## Support

### Check These First
1. Frontend builds without errors
2. Backend is running on port 8000
3. Browser console shows no errors
4. API keys configured in `.env`

### Common Issues
- **Port in use**: Kill process on port 3000
- **API errors**: Check `.env` has valid keys
- **Styling issues**: Clear cache, rebuild frontend

---

**Status**: ✅ Complete and ready to use
**Date**: February 5, 2026
**Version**: 1.0
