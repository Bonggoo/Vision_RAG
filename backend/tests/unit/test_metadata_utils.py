"""
metadata_service.py 순수 유틸 함수 단위 테스트.
GCS 연결 없이 검증 가능한 경로 생성 함수만.
"""
import pytest
from app.services.metadata_service import gcs_doc_prefix, gcs_blob_path


class TestGcsDocPrefix:
    def test_basic_path(self):
        result = gcs_doc_prefix("user@example.com", "doc-123")
        assert result == "users/user@example.com/doc-123"

    def test_email_lowercased(self):
        result = gcs_doc_prefix("USER@EXAMPLE.COM", "doc-abc")
        assert result == "users/user@example.com/doc-abc"

    def test_no_trailing_slash(self):
        result = gcs_doc_prefix("a@b.com", "id1")
        assert not result.endswith("/")

    def test_path_structure(self):
        result = gcs_doc_prefix("test@test.com", "uuid-001")
        parts = result.split("/")
        assert parts[0] == "users"
        assert parts[1] == "test@test.com"
        assert parts[2] == "uuid-001"


class TestGcsBlobPath:
    def test_metadata_json_path(self):
        result = gcs_blob_path("user@example.com", "doc-123", "metadata.json")
        assert result == "users/user@example.com/doc-123/metadata.json"

    def test_original_pdf_path(self):
        result = gcs_blob_path("a@b.com", "id1", "original.pdf")
        assert result == "users/a@b.com/id1/original.pdf"

    def test_is_extension_of_doc_prefix(self):
        prefix = gcs_doc_prefix("a@b.com", "id1")
        blob = gcs_blob_path("a@b.com", "id1", "toc.json")
        assert blob.startswith(prefix + "/")
