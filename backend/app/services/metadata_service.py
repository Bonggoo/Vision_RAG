"""
문서 메타데이터 관리 서비스 (GCS 연동).

Google Cloud Storage(GCS)를 기반으로 문서 CRUD를 수행합니다.
"""
import os
import json
import shutil
from typing import List, Dict, Any, Optional
from google.cloud import storage
from app.config import settings

def _get_bucket():
    client = storage.Client()
    return client.bucket(settings.GCS_BUCKET_NAME)

def get_all_documents() -> List[Dict[str, Any]]:
    """
    GCS 버킷에서 모든 문서 메타데이터를 조회합니다.
    """
    documents = []
    try:
        bucket = _get_bucket()
        # metadata.json 파일들만 찾습니다
        blobs = bucket.list_blobs(match_glob="*/metadata.json")
        for blob in blobs:
            try:
                content = blob.download_as_text()
                meta = json.loads(content)
                documents.append(meta)
            except Exception as e:
                print(f"Error reading {blob.name}: {e}")
                continue
    except Exception as e:
        print(f"GCS list error: {e}")

    # 업로드 시간 역순 정렬
    documents.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return documents

def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 반환합니다.
    """
    try:
        bucket = _get_bucket()
        blob = bucket.blob(f"{document_id}/metadata.json")
        if not blob.exists():
            return None
        content = blob.download_as_text()
        return json.loads(content)
    except Exception as e:
        print(f"GCS get error: {e}")
        return None

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
    GCS에서 다운로드하여 /tmp 공간에 캐싱합니다.
    """
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
    pdf_path = os.path.join(doc_dir, "original.pdf")
    
    # 캐시 확인
    if os.path.isfile(pdf_path):
        return pdf_path
        
    # GCS에서 다운로드
    try:
        os.makedirs(doc_dir, exist_ok=True)
        bucket = _get_bucket()
        blob = bucket.blob(f"{document_id}/original.pdf")
        if not blob.exists():
            return None
            
        blob.download_to_filename(pdf_path)
        return pdf_path
    except Exception as e:
        print(f"GCS download error: {e}")
        return None

def update_document_metadata(document_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 업데이트합니다.
    """
    meta = get_document(document_id)
    if meta is None:
        return None

    meta.update(updates)
    try:
        bucket = _get_bucket()
        blob = bucket.blob(f"{document_id}/metadata.json")
        blob.upload_from_string(json.dumps(meta, ensure_ascii=False, indent=2), content_type="application/json")
    except Exception as e:
        print(f"GCS update error: {e}")
        return None

    return meta

def delete_document(document_id: str) -> bool:
    """
    GCS에서 문서 디렉토리 전체를 삭제합니다 (PDF + metadata.json).
    그리고 로컬 캐시(/tmp)도 삭제합니다.
    """
    # 1. GCS 삭제
    try:
        bucket = _get_bucket()
        blobs = bucket.list_blobs(prefix=f"{document_id}/")
        for blob in blobs:
            blob.delete()
    except Exception as e:
        print(f"GCS delete error: {e}")
        return False
        
    # 2. 로컬 캐시 삭제
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
    if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir)
        
    return True
