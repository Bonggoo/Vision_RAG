import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_documents_success(monkeypatch):
    """
    GET /documents 정상 동작 테스트
    """
    # 임시 목업
    def mock_get_all(owner_email=None):
        import uuid
        from datetime import datetime
        return [{
            "document_id": str(uuid.UUID("12345678-1234-5678-1234-567812345678")),
            "filename": "test.pdf",
            "total_pages": 10,
            "uploaded_at": datetime.now().isoformat()
        }]
    
    monkeypatch.setattr("app.routers.documents.metadata_service.get_all_documents", mock_get_all, raising=False)
    
    response = client.get("/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert len(data["documents"]) == 1
    assert data["documents"][0]["filename"] == "test.pdf"

def test_delete_document_success(monkeypatch):
    """
    DELETE /documents/{id} 정상 동작 테스트
    """
    def mock_delete(doc_id, owner_email=None):
        return True
        
    monkeypatch.setattr("app.routers.documents.metadata_service.delete_document", mock_delete, raising=False)
    monkeypatch.setattr("app.routers.documents.metadata_service.verify_document_owner", lambda doc_id, owner_email: True, raising=False)
    
    response = client.delete("/documents/12345678-1234-5678-1234-567812345678")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
