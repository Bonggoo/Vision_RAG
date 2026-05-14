"""
문서 메타데이터 관리 서비스.

uploads 디렉토리의 metadata.json 파일을 기반으로 문서 CRUD를 수행합니다.
"""
import os
import json
import shutil
from uuid import UUID
from typing import List, Dict, Any, Optional
from app.config import settings


def get_all_documents() -> List[Dict[str, Any]]:
    """
    uploads 디렉토리의 모든 문서 메타데이터를 조회합니다.
    각 문서는 uploads/{document_id}/metadata.json 형태로 저장됩니다.
    """
    documents = []
    upload_dir = settings.PDF_UPLOAD_DIR

    if not os.path.exists(upload_dir):
        return documents

    for dir_name in os.listdir(upload_dir):
        meta_path = os.path.join(upload_dir, dir_name, "metadata.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                documents.append(meta)
            except (json.JSONDecodeError, IOError):
                continue

    # 업로드 시간 역순 정렬
    documents.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return documents


def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 반환합니다.
    """
    meta_path = os.path.join(settings.PDF_UPLOAD_DIR, document_id, "metadata.json")
    if not os.path.isfile(meta_path):
        return None

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_document_toc(document_id: str) -> List[Dict[str, Any]]:
    """
    특정 문서의 ToC(목차)를 반환합니다.
    """
    meta = get_document(document_id)
    if meta is None:
        return []
    return meta.get("toc", [])


def get_document_path(document_id: str) -> Optional[str]:
    """
    특정 문서의 원본 PDF 경로를 반환합니다.
    """
    pdf_path = os.path.join(settings.PDF_UPLOAD_DIR, document_id, "original.pdf")
    if os.path.isfile(pdf_path):
        return pdf_path
    return None


def update_document_metadata(document_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 업데이트합니다.
    """
    meta = get_document(document_id)
    if meta is None:
        return None

    meta.update(updates)
    meta_path = os.path.join(settings.PDF_UPLOAD_DIR, document_id, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


def delete_document(document_id: str) -> bool:
    """
    문서 디렉토리 전체를 삭제합니다 (PDF + metadata.json).
    """
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
    if not os.path.isdir(doc_dir):
        return False

    shutil.rmtree(doc_dir)
    return True
