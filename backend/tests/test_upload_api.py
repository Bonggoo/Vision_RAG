import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)

dummy_pdf_content = b"%PDF-1.4 dummy content"

def test_upload_endpoint_success(monkeypatch):
    """
    POST /upload 정상 동작 테스트 (TDD Red -> Green)
    """
    # pdf_service의 process_document_upload를 모킹
    async def mock_process(file, owner_email=None):
        import uuid
        return {
            "document_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "filename": "test.pdf",
            "total_pages": 10,
            "toc": [{"level": 1, "title": "Chapter 1", "page": 1}],
            "status": "indexed"
        }
    
    # 패치 적용 (라우터 구현 시 의존성에 따라 수정 필요)
    monkeypatch.setattr("app.routers.upload.process_document_upload", mock_process, raising=False)
    
    response = client.post("/upload", files={"file": ("test.pdf", dummy_pdf_content, "application/pdf")})
    
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test.pdf"
    assert data["total_pages"] == 10
    assert data["status"] == "indexed"
    assert len(data["toc"]) == 1
    assert "document_id" in data
