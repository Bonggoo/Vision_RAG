"""
비-PDF 문서 업로드(멀티포맷) 통합 테스트.

업로드 검증 → preflight blob/content-type → 분석 파이프라인 내 PDF 변환 →
원본 파일 다운로드까지, 'PDF 정규화' 전략의 라우터/서비스 계층을 검증합니다.
"""
import asyncio
import json
import os
import shutil
import uuid

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services import metadata_service

client = TestClient(app)

DEV_USER_EMAIL = "local-dev@visionrag.app"  # 로컬 모드 더미 유저 (auth_service)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _make_doc_dir(doc_id: str, metadata: dict, files: dict[str, bytes] | None = None) -> str:
    """로컬 스토리지 규약대로 문서 디렉토리를 구성합니다."""
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
    shutil.rmtree(doc_dir, ignore_errors=True)
    os.makedirs(doc_dir, exist_ok=True)
    with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    for name, data in (files or {}).items():
        with open(os.path.join(doc_dir, name), "wb") as f:
            f.write(data)
    metadata_service.invalidate_documents_cache()
    return doc_dir


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    return doc.tobytes()


# ── POST /upload 확장자 검증 ─────────────────────────────────────────────────

class TestUploadValidation:
    def test_rejects_unsupported_extension(self):
        res = client.post("/upload", files={"file": ("virus.exe", b"MZ...", "application/octet-stream")})
        assert res.status_code == 400
        assert "지원" in res.json()["detail"]

    def test_accepts_docx(self, monkeypatch):
        async def mock_process(file, owner_email=None):
            return {
                "document_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
                "filename": "사양서",
                "total_pages": 2,
                "toc": [],
                "status": "indexed",
                "source_format": "docx",
            }
        monkeypatch.setattr("app.routers.upload.process_document_upload", mock_process)

        res = client.post("/upload", files={"file": ("사양서.docx", b"PK\x03\x04...", DOCX_MIME)})
        assert res.status_code == 200
        assert res.json()["source_format"] == "docx"


# ── POST /upload/preflight ──────────────────────────────────────────────────

class TestPreflight:
    def test_rejects_unsupported_extension(self):
        res = client.post("/upload/preflight", json={
            "file_hash": "a" * 64, "file_size": 100, "filename": "archive.zip",
        })
        assert res.status_code == 400

    def test_returns_content_type_for_docx(self, monkeypatch):
        async def mock_all_docs(owner_email=None):
            return []
        monkeypatch.setattr("app.routers.upload.metadata_service.get_all_documents_async", mock_all_docs)

        res = client.post("/upload/preflight", json={
            "file_hash": "b" * 64, "file_size": 100, "filename": "사양서.docx",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["content_type"] == DOCX_MIME
        assert data["upload_url"] is None  # 로컬 모드는 동기 업로드 fallback

    def test_returns_pdf_content_type_for_pdf(self, monkeypatch):
        async def mock_all_docs(owner_email=None):
            return []
        monkeypatch.setattr("app.routers.upload.metadata_service.get_all_documents_async", mock_all_docs)

        res = client.post("/upload/preflight", json={
            "file_hash": "c" * 64, "file_size": 100, "filename": "manual.pdf",
        })
        assert res.status_code == 200
        assert res.json()["content_type"] == "application/pdf"


# ── POST /upload/analyze 원본 존재 검증 (비-PDF blob 이름) ───────────────────

class TestTriggerAnalysis:
    def test_missing_source_returns_404(self):
        res = client.post("/upload/analyze", json={
            "document_id": str(uuid.uuid4()), "filename": "ghost.docx", "file_hash": "d" * 64,
        })
        assert res.status_code == 404

    def test_finds_non_pdf_source_and_records_format(self, monkeypatch):
        doc_id = str(uuid.uuid4())
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        with open(os.path.join(doc_dir, "source_original.docx"), "wb") as f:
            f.write(b"PK\x03\x04fake")

        captured = {}

        async def mock_create(document_id, metadata, owner_email):
            captured.update(metadata)
            return True

        async def mock_enqueue(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.routers.upload.metadata_service.create_document_metadata_async", mock_create
        )
        monkeypatch.setattr("app.services.task_queue.enqueue_analysis", mock_enqueue)

        res = client.post("/upload/analyze", json={
            "document_id": doc_id, "filename": "사양서.docx", "file_hash": "e" * 64,
        })
        assert res.status_code == 200
        assert captured.get("source_format") == "docx"
        shutil.rmtree(doc_dir, ignore_errors=True)


# ── 비동기 분석 파이프라인의 변환 단계 ───────────────────────────────────────

class TestAnalysisPipelineConversion:
    def test_txt_source_converted_to_original_pdf(self, monkeypatch):
        from app.routers.upload import _run_analysis_pipeline

        doc_id = str(uuid.uuid4())
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        with open(os.path.join(doc_dir, "source_original.txt"), "w", encoding="utf-8") as f:
            f.write("설비 점검 절차서\n압력 게이지를 확인합니다.\n")
        with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"document_id": doc_id, "status": "analyzing", "owner_email": DEV_USER_EMAIL}, f)

        async def mock_classification(pdf_path, fallback):
            return {"title": "설비 점검 절차서", "manufacturer": None,
                    "model_series": None, "doc_type": None}

        monkeypatch.setattr("app.routers.upload._extract_document_classification", mock_classification)
        monkeypatch.setattr(
            "app.routers.upload.build_toc",
            lambda doc, total: ([{"level": 1, "title": "점검", "page": 1}], "indexed"),
        )
        metadata_service.invalidate_documents_cache()

        asyncio.run(_run_analysis_pipeline(doc_id, "절차서.txt", "f" * 64, DEV_USER_EMAIL))

        pdf_path = os.path.join(doc_dir, "original.pdf")
        assert os.path.isfile(pdf_path), "변환된 original.pdf가 생성되어야 함"
        converted = fitz.open(pdf_path)
        assert "설비 점검 절차서" in converted[0].get_text()

        with open(os.path.join(doc_dir, "metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["status"] == "indexed"
        assert meta["source_format"] == "txt"
        shutil.rmtree(doc_dir, ignore_errors=True)

    def test_conversion_failure_sets_error_status(self, monkeypatch):
        from app.routers.upload import _run_analysis_pipeline

        doc_id = str(uuid.uuid4())
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        # png 확장자인데 실제로는 이미지가 아닌 파일 → 시그니처 검증 실패
        with open(os.path.join(doc_dir, "source_original.png"), "wb") as f:
            f.write(b"not an image")
        with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"document_id": doc_id, "status": "analyzing", "owner_email": DEV_USER_EMAIL}, f)
        metadata_service.invalidate_documents_cache()

        asyncio.run(_run_analysis_pipeline(doc_id, "사진.png", "0" * 64, DEV_USER_EMAIL))

        with open(os.path.join(doc_dir, "metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["status"] == "error"
        assert meta.get("error_message")
        shutil.rmtree(doc_dir, ignore_errors=True)


# ── 동기 업로드 경로 (process_document_upload) ──────────────────────────────

class TestSyncUploadConversion:
    def test_txt_upload_stores_source_and_pdf(self, monkeypatch):
        from app.services.pdf_service import process_document_upload
        from fastapi import UploadFile
        import io

        async def mock_classification(pdf_path, fallback):
            return {"title": "점검 일지", "manufacturer": None,
                    "model_series": None, "doc_type": None}

        async def mock_all_docs(owner_email=None):
            return []

        monkeypatch.setattr(
            "app.services.pdf_service._extract_document_classification", mock_classification
        )
        monkeypatch.setattr(
            "app.services.pdf_service.build_toc",
            lambda doc, total: ([], "indexed"),
        )
        monkeypatch.setattr(
            "app.services.pdf_service.metadata_service.get_all_documents_async", mock_all_docs
        )

        content = "설비 점검 일지\n모터 온도 정상\n".encode("utf-8")
        upload = UploadFile(filename="일지.txt", file=io.BytesIO(content))

        result = asyncio.run(process_document_upload(upload, owner_email=DEV_USER_EMAIL))

        assert result["source_format"] == "txt"
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, result["document_id"])
        assert os.path.isfile(os.path.join(doc_dir, "source_original.txt"))
        assert os.path.isfile(os.path.join(doc_dir, "original.pdf"))
        converted = fitz.open(os.path.join(doc_dir, "original.pdf"))
        assert "설비 점검 일지" in converted[0].get_text()
        shutil.rmtree(doc_dir, ignore_errors=True)


# ── metadata_service blob 파일명 파라미터화 ──────────────────────────────────

class TestGetDocumentPathBlobParam:
    def test_custom_blob_filename_local(self):
        doc_id = str(uuid.uuid4())
        doc_dir = _make_doc_dir(doc_id, {"document_id": doc_id}, {
            "source_original.docx": b"PK\x03\x04fake",
        })

        path = metadata_service.get_document_path(
            doc_id, owner_email=DEV_USER_EMAIL, blob_filename="source_original.docx"
        )
        assert path == os.path.join(doc_dir, "source_original.docx")
        shutil.rmtree(doc_dir, ignore_errors=True)

    def test_default_remains_original_pdf(self):
        doc_id = str(uuid.uuid4())
        doc_dir = _make_doc_dir(doc_id, {"document_id": doc_id}, {
            "original.pdf": _minimal_pdf_bytes(),
        })

        path = metadata_service.get_document_path(doc_id, owner_email=DEV_USER_EMAIL)
        assert path == os.path.join(doc_dir, "original.pdf")
        shutil.rmtree(doc_dir, ignore_errors=True)


# ── 원본 다운로드 (source_format 분기) ───────────────────────────────────────

class TestDownloadSourceOriginal:
    def _setup_docx_doc(self):
        doc_id = str(uuid.uuid4())
        doc_dir = _make_doc_dir(doc_id, {
            "document_id": doc_id,
            "filename": "사양서",
            "owner_email": DEV_USER_EMAIL,
            "status": "indexed",
            "source_format": "docx",
        }, {
            "source_original.docx": b"PK\x03\x04fake-docx-bytes",
            "original.pdf": _minimal_pdf_bytes(),
        })
        return doc_id, doc_dir

    def test_download_serves_original_docx(self):
        doc_id, doc_dir = self._setup_docx_doc()
        res = client.get(f"/documents/{doc_id}/download")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith(DOCX_MIME)
        assert ".docx" in res.headers.get("content-disposition", "")
        assert res.content == b"PK\x03\x04fake-docx-bytes"
        shutil.rmtree(doc_dir, ignore_errors=True)

    def test_download_url_filename_has_source_extension(self):
        doc_id, doc_dir = self._setup_docx_doc()
        res = client.get(f"/documents/{doc_id}/download-url")
        assert res.status_code == 200
        data = res.json()
        assert data["filename"].endswith(".docx")
        shutil.rmtree(doc_dir, ignore_errors=True)

    def test_download_pdf_document_unchanged(self):
        doc_id = str(uuid.uuid4())
        doc_dir = _make_doc_dir(doc_id, {
            "document_id": doc_id,
            "filename": "매뉴얼",
            "owner_email": DEV_USER_EMAIL,
            "status": "indexed",
        }, {
            "original.pdf": _minimal_pdf_bytes(),
        })
        res = client.get(f"/documents/{doc_id}/download")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/pdf")
        shutil.rmtree(doc_dir, ignore_errors=True)
