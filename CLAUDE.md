# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Vision_RAG ("TechNote") — Agentic PDF RAG system. The AI navigates industrial manuals like a human (reads ToC → jumps to page → Vision analysis), no vector DB required.

**Stack:**
- Frontend: Next.js + Tailwind + PWA (`frontend/`)
- Backend: FastAPI + Google Cloud Storage + Gemini via the `google-genai` SDK (`backend/`)

## Commands

```bash
# Backend (from backend/)
source venv/bin/activate
uvicorn app.main:app --reload

# Frontend (from frontend/) — check package.json for scripts
npm run dev

# Unit tests (from backend/)
pytest

# Quality evals (from backend/, venv active) — see backend/evals/README.md
python -m evals.run_eval             # golden dataset vs deployed Cloud Run backend (needs EVAL_JWT_SECRET in .env)
python -m evals.run_eval --local     # same, but calls the pipeline in-process (no server)
python -m evals.run_eval --judge     # include LLM-as-judge scoring
```

## Architecture — 3-phase retrieval

1. **Phase 0+1** (Flash-Lite, text-only): Select the relevant document from the sidebar + extract ToC hierarchy.
2. **Phase 2** (text search): Pinpoint the exact section using keyword matching against extracted text.
3. **Phase 3** (Vision): Send the raw PDF page image to Gemini Vision for final answer synthesis.

- `backend/app/services/agentic_graph.py` — orchestrates the phases as a graph.
- `backend/app/services/pdf_service.py` — GCS Signed URL generation and sparse-PDF patching.
- `backend/app/routers/` — `auth`, `chat`, `conversations`, `documents`, `upload`, `internal`.
- `backend/evals/` — golden-dataset quality eval harness (routing/document/page/keyword checks + optional LLM-as-judge). See `backend/evals/README.md`.

**Auth:** Google OAuth → JWT (access + refresh). `backend/app/routers/auth.py` + `services/auth_service.py`. All routes require JWT except health check.

**Storage:** PDFs live in GCS. Pre-flight SHA-256 hash check prevents duplicate uploads (returns 409). Direct browser→GCS upload (server memory bypass) for large files. Non-PDF uploads (docx/xlsx/pptx/txt/md/images) are normalized to PDF at ingestion (`backend/app/services/document_conversion.py` — LibreOffice headless / PyMuPDF) and stored as `original.pdf` so the ToC/Vision pipeline runs unchanged; the raw upload is kept as `source_original.{ext}` and served on download.

**Deployment:** `cloudbuild.yaml` + `Dockerfile` in `backend/`. Frontend deploys to Vercel.

## Frontend (`frontend/src/`)

Next.js App Router + Zustand + Tailwind PWA. Chat streams over SSE.

- **State (`store/`):** `useAuthStore` (Google OAuth + JWT refresh; tolerates transient refresh failures — only force-logs-out on a real 401), `useDocumentStore` (sidebar docs + upload), `useChatStore` (conversation), `useUIStore` (global toasts + confirm dialog).
- **UX primitives — do NOT use native `alert()`/`confirm()`.** Use the `useUIStore` helpers, which work outside React too:
  - `toast.success/error/info/warning(message, { title?, duration? })` — rendered by `components/ui/Toaster.tsx` (mounted in `app/layout.tsx`).
  - `confirmDialog({ title, description?, danger?, ... })` → `Promise<boolean>` — rendered by `components/ui/ConfirmDialog.tsx`.
- **Upload:** `lib/upload.ts` `processUploadFiles()` is the shared handler for both the sidebar and the welcome-screen onboarding; it summarizes success/duplicate/error counts into a toast and refreshes the doc list.
- `app/page.tsx` shows an adaptive welcome/onboarding screen when the user has no documents yet.
