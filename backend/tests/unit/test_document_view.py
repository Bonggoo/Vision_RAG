"""참조 페이지 원본 PDF 보기 엔드포인트 테스트 (remaining_tasks P3 — 방향 B)."""
import json
import os

import fitz
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware import rate_limit

DOC_ID = "11111111-2222-3333-4444-555555555555"
LOCAL_USER = "local-dev@visionrag.app"   # USE_LOCAL_STORAGE 모드의 더미 사용자


@pytest.fixture
def client(tmp_path, monkeypatch):
    """로컬 스토리지 모드에 3쪽짜리 문서 하나를 심어 둔 TestClient."""
    monkeypatch.setattr(settings, "PDF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "USE_LOCAL_STORAGE", True)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    rate_limit.reset()

    doc_dir = tmp_path / DOC_ID
    doc_dir.mkdir()

    pdf = fitz.open()
    for i in range(3):
        pdf.new_page().insert_text((72, 72), f"page {i + 1}")
    pdf.save(str(doc_dir / "original.pdf"))
    pdf.close()

    (doc_dir / "metadata.json").write_text(json.dumps({
        "document_id": DOC_ID,
        "filename": "테스트 매뉴얼.pdf",
        "owner_email": LOCAL_USER,
        "manufacturer": "미쓰비시",
        "model_series": "MELSEC-Q",
        "doc_type": "사용자매뉴얼",
        "source_format": "pdf",
    }, ensure_ascii=False), encoding="utf-8")

    from app.main import app
    with TestClient(app) as c:
        yield c
    rate_limit.reset()


def test_view_url은_로컬_보기_경로를_준다(client):
    res = client.get(f"/documents/{DOC_ID}/view-url")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "local"
    assert body["url"] == f"/documents/{DOC_ID}/view"
    assert body["filename"].endswith(".pdf")


def test_view는_inline으로_PDF를_서빙한다(client):
    """attachment 면 브라우저가 저장해 버려서 `#page=N` 이 무시된다."""
    res = client.get(f"/documents/{DOC_ID}/view")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("inline")
    assert res.content.startswith(b"%PDF")


def test_다운로드는_여전히_attachment다(client):
    """보기 경로를 추가하면서 기존 다운로드 동작이 바뀌지 않아야 한다."""
    res = client.get(f"/documents/{DOC_ID}/download")
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("attachment")


def test_남의_문서는_403(client, monkeypatch):
    from app.services import auth_service

    monkeypatch.setitem(
        client.app.dependency_overrides, auth_service.get_current_user,
        lambda: {"email": "someone-else@example.com", "name": "", "picture": ""},
    )
    assert client.get(f"/documents/{DOC_ID}/view-url").status_code == 403
    assert client.get(f"/documents/{DOC_ID}/view").status_code == 403


def test_없는_문서는_403이나_404(client):
    missing = "99999999-9999-9999-9999-999999999999"
    assert client.get(f"/documents/{missing}/view-url").status_code in (403, 404)


def test_inline_signed_url은_disposition을_그대로_쓴다():
    """GCS 모드에서 inline 이 서명에 반영되는지 (문자열 조립 지점) 확인."""
    from app.services import metadata_service

    captured = {}

    def fake_sign(**kwargs):
        captured.update(kwargs)
        return "https://storage.googleapis.com/signed"

    orig_local = settings.USE_LOCAL_STORAGE
    orig_sign = metadata_service.generate_gcs_signed_url
    try:
        settings.USE_LOCAL_STORAGE = False
        metadata_service.generate_gcs_signed_url = fake_sign
        metadata_service.get_document_signed_url(
            DOC_ID, "매뉴얼.pdf", owner_email=LOCAL_USER, disposition="inline"
        )
    finally:
        settings.USE_LOCAL_STORAGE = orig_local
        metadata_service.generate_gcs_signed_url = orig_sign

    assert captured["response_content_disposition"].startswith("inline;")
