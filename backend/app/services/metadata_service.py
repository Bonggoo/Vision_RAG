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

from app.utils.logger import logger

def _get_bucket():
    client = storage.Client()
    return client.bucket(settings.GCS_BUCKET_NAME)

def get_all_documents() -> List[Dict[str, Any]]:
    """
    모든 문서 메타데이터를 조회합니다.
    USE_LOCAL_STORAGE=True인 경우 로컬 파일 시스템에서, 그렇지 않은 경우 GCS에서 조회합니다.
    """
    documents = []
    
    if settings.USE_LOCAL_STORAGE:
        # 로컬 스토리지에서 조회
        logger.info("📁 로컬 파일 시스템에서 문서 목록 조회 중...")
        try:
            if not os.path.exists(settings.PDF_UPLOAD_DIR):
                return []
            for doc_id in os.listdir(settings.PDF_UPLOAD_DIR):
                doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
                if os.path.isdir(doc_dir):
                    meta_path = os.path.join(doc_dir, "metadata.json")
                    if os.path.isfile(meta_path):
                        try:
                            with open(meta_path, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                                documents.append(meta)
                        except Exception as e:
                            logger.error(f"로컬 메타데이터 로드 실패 ({meta_path}): {e}")
        except Exception as e:
            logger.error(f"로컬 디렉토리 탐색 오류: {e}")
    else:
        # GCS에서 조회
        logger.info("☁️ GCS 버킷에서 문서 목록 조회 중...")
        try:
            bucket = _get_bucket()
            blobs = bucket.list_blobs(match_glob="*/metadata.json")
            for blob in blobs:
                try:
                    content = blob.download_as_text()
                    meta = json.loads(content)
                    documents.append(meta)
                except Exception as e:
                    logger.error(f"Error reading {blob.name}: {e}")
                    continue
        except Exception as e:
            logger.error(f"GCS list error: {e}")

    # 업로드 시간 역순 정렬
    documents.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return documents

def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 반환합니다.
    """
    if settings.USE_LOCAL_STORAGE:
        meta_path = os.path.join(settings.PDF_UPLOAD_DIR, document_id, "metadata.json")
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"로컬 메타데이터 단건 로드 실패 ({meta_path}): {e}")
            return None
    else:
        try:
            bucket = _get_bucket()
            blob = bucket.blob(f"{document_id}/metadata.json")
            if not blob.exists():
                return None
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            logger.error(f"GCS get error: {e}")
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
    로컬인 경우 로컬 경로를 반환하고, GCS인 경우 캐시(/tmp) 경로를 확인 후 다운로드합니다.
    """
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
    pdf_path = os.path.join(doc_dir, "original.pdf")
    
    if settings.USE_LOCAL_STORAGE:
        if os.path.isfile(pdf_path):
            return pdf_path
        return None
        
    # GCS 환경에서의 로직 (캐시 확인 및 다운로드)
    if os.path.isfile(pdf_path):
        return pdf_path
        
    try:
        os.makedirs(doc_dir, exist_ok=True)
        bucket = _get_bucket()
        blob = bucket.blob(f"{document_id}/original.pdf")
        if not blob.exists():
            return None
            
        blob.download_to_filename(pdf_path)
        return pdf_path
    except Exception as e:
        logger.error(f"GCS download error: {e}")
        return None

def update_document_metadata(document_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 업데이트합니다.
    """
    meta = get_document(document_id)
    if meta is None:
        return None

    meta.update(updates)
    
    if settings.USE_LOCAL_STORAGE:
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
        os.makedirs(doc_dir, exist_ok=True)
        meta_path = os.path.join(doc_dir, "metadata.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            return meta
        except Exception as e:
            logger.error(f"로컬 메타데이터 업데이트 실패: {e}")
            return None
    else:
        try:
            bucket = _get_bucket()
            blob = bucket.blob(f"{document_id}/metadata.json")
            blob.upload_from_string(json.dumps(meta, ensure_ascii=False, indent=2), content_type="application/json")
            return meta
        except Exception as e:
            logger.error(f"GCS update error: {e}")
            return None

def delete_document(document_id: str) -> bool:
    """
    문서 디렉토리 전체를 삭제합니다.
    """
    # 1. 스토리지 삭제
    if settings.USE_LOCAL_STORAGE:
        logger.info(f"📁 로컬 스토리지에서 문서 삭제 중: {document_id}")
    else:
        logger.info(f"☁️ GCS에서 문서 삭제 중: {document_id}")
        try:
            bucket = _get_bucket()
            blobs = bucket.list_blobs(prefix=f"{document_id}/")
            for blob in blobs:
                blob.delete()
        except Exception as e:
            logger.error(f"GCS delete error: {e}")
            return False
        
    # 2. 로컬 디렉토리 삭제 (GCS의 경우 캐시 삭제, 로컬의 경우 주 저장소 삭제)
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, document_id)
    if os.path.isdir(doc_dir):
        try:
            shutil.rmtree(doc_dir)
        except Exception as e:
            logger.error(f"로컬 디렉토리 삭제 실패 ({doc_dir}): {e}")
            return False
        
    return True

