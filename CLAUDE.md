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
USE_LOCAL_STORAGE=False python -m evals.run_eval --local   # in-process pipeline; the override is REQUIRED — eval documents live in GCS, and the .env default (True) yields 0 documents
python -m evals.run_eval --judge     # include LLM-as-judge scoring
```

## Architecture — 3-phase retrieval

1. **Phase 0+1** (Flash-Lite, text-only): Select the relevant document from the sidebar + extract ToC hierarchy.
2. **Phase 2** (text search): Pinpoint the exact section using keyword matching against extracted text.
3. **Phase 3** (Vision): Send the raw PDF page image to Gemini Vision for final answer synthesis.

- `backend/app/services/agentic/` — the pipeline, split by role. Import `run_agentic_pipeline` from the package; everything else is internal.
  - `pipeline.py` — stage orchestration (image analysis → quick classify → document resolution → answer).
  - `context.py` — `PipelineContext`: shared state, SSE event builders, conversation save.
  - `llm_steps.py` — per-phase LLM calls (document select, page select, text refine, fallbacks).
  - `doc_filter.py` — keyword-based first-pass document filter and related pure functions.
  - `toc.py` / `classification.py` / `sse.py` — page-number normalization, rule-based routing, SSE serialization.
- `backend/app/prompts.py` — every LLM prompt template. Do not inline prompts in service code.
  - **Variable order matters for cost.** Gemini implicit caching only discounts a shared prompt *prefix*, so large/stable content (ToC, section text, PDF part, document list) must come **before** variable content (chat context, previous reference, question). Functions carrying a `⚠️ 변수 순서 주의` docstring are ordered deliberately — reordering them silently breaks cache hits (Phase 2 measured 0% → 95% from this alone). See `docs/context-management-results.md`.
  - `chat_context_section()` is the single source of chat-history truncation (6 messages × 300 chars, matching what the frontend sends). Do not re-implement slicing at call sites.
- `backend/app/utils/llm_usage.py` — per-call token/cache metering. Every chat-path Gemini call logs `🧮 [Usage] <stage>: in=… out=… cached=… (…%)`; `cached` comes from `usage_metadata.input_token_details.cache_read`.
- `backend/app/services/pdf_service.py` — GCS Signed URL generation and sparse-PDF patching.
- `backend/app/routers/` — `auth`, `chat`, `conversations`, `documents`, `upload`, `internal`.
- `backend/evals/` — golden-dataset quality eval harness (routing/document/page/keyword checks + optional LLM-as-judge). See `backend/evals/README.md`.

**Auth:** Google OAuth → JWT (access + refresh). `backend/app/routers/auth.py` + `services/auth_service.py`. All routes require JWT except health check.

**Storage:** PDFs live in GCS. Pre-flight SHA-256 hash check prevents duplicate uploads (returns 409). Direct browser→GCS upload (server memory bypass) for large files. Non-PDF uploads (docx/xlsx/pptx/txt/md/images) are normalized to PDF at ingestion (`backend/app/services/document_conversion.py` — LibreOffice headless / PyMuPDF) and stored as `original.pdf` so the ToC/Vision pipeline runs unchanged; the raw upload is kept as `source_original.{ext}` and served on download.

**Local dev mode (`USE_LOCAL_STORAGE=True`):** all storage — documents (`metadata_service`, `pdf_service`, `upload`) **and** conversation history (`conversation_service`) — falls back to the local filesystem, so the full pipeline (upload → ToC → chat → conversation save) runs offline with only the Gemini API as an external dependency. Docs write under `PDF_UPLOAD_DIR`; conversations under a sibling `conversations/{email}/{session_id}.json`. GCS is never touched in this mode. Every GCS call site is gated behind this flag.

**Deployment — unified origin (frontend and backend ship together):** `cloudbuild.yaml` + `Dockerfile` in `backend/`. The Cloud Build trigger fires on pushes to `master` that touch `backend/**` **or** `frontend/**`. Step 0 builds the Next.js static export with `NEXT_PUBLIC_API_URL=` (empty, so API calls become same-origin relative paths) and copies `frontend/out` to `backend/static/`; the remaining steps build the image, push it, and deploy a new Cloud Run revision (`vision-rag-backend`, `asia-northeast3`). So `/` serves the frontend and `/api/*` the backend from one domain — this is what keeps the iOS login session alive. There is no separate frontend host; Vercel is no longer used. Health check is `/api/health` (never `/healthz` — Cloud Run reserves it). Builds take ~6-7 min.

## Frontend (`frontend/src/`)

Next.js App Router + Zustand + Tailwind PWA. Chat streams over SSE.

- **State (`store/`):** `useAuthStore` (Google OAuth + JWT refresh; tolerates transient refresh failures — only force-logs-out on a real 401), `useDocumentStore` (sidebar docs + upload), `useChatStore` (conversation), `useUIStore` (global toasts + confirm dialog).
- **UX primitives — do NOT use native `alert()`/`confirm()`.** Use the `useUIStore` helpers, which work outside React too:
  - `toast.success/error/info/warning(message, { title?, duration? })` — rendered by `components/ui/Toaster.tsx` (mounted in `app/layout.tsx`).
  - `confirmDialog({ title, description?, danger?, ... })` → `Promise<boolean>` — rendered by `components/ui/ConfirmDialog.tsx`.
- **Upload:** `lib/upload.ts` `processUploadFiles()` is the shared handler for both the sidebar and the welcome-screen onboarding; it summarizes success/duplicate/error counts into a toast and refreshes the doc list.
- `app/page.tsx` shows an adaptive welcome/onboarding screen when the user has no documents yet.
