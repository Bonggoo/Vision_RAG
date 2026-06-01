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

def get_all_documents(owner_email: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    모든 문서 메타데이터를 조회합니다.
    USE_LOCAL_STORAGE=True인 경우 로컬 파일 시스템에서, 그렇지 않은 경우 GCS에서 조회합니다.
    owner_email이 주어지면 해당 사용자 소유 문서 + 레거시(공용) 문서만 반환합니다.
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

    # 사용자별 필터링: 엄격 격리 — 본인 소유 문서만 반환 (레거시 문서도 차단)
    if owner_email:
        email_lower = owner_email.lower()
        # 디버깅: 필터링 전 각 문서의 owner_email 확인
        for d in documents:
            logger.info(f"🔍 [격리 필터] 문서 '{d.get('filename', '?')}' owner_email='{d.get('owner_email')}' vs 요청='{email_lower}'")
        
        before_count = len(documents)
        documents = [
            d for d in documents
            if d.get("owner_email", "").lower() == email_lower
        ]
        logger.info(f"🔒 [격리 결과] {before_count}건 → {len(documents)}건 (요청자: {email_lower})")

    # 업로드 시간 역순 정렬
    documents.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return documents


def verify_document_owner(document_id: str, owner_email: str) -> bool:
    """문서 소유권을 검증합니다. 엄격 격리: 본인 소유 문서만 허용."""
    meta = get_document(document_id)
    if meta is None:
        return False
    doc_owner = meta.get("owner_email")
    if doc_owner is None:
        return False  # 레거시 문서(소유자 미배정)는 접근 차단
    return doc_owner.lower() == owner_email.lower()

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

def generate_gcs_signed_url(bucket_name: str, blob_name: str, method: str, expiration_minutes: int, content_type: str = None, response_content_disposition: str = None) -> Optional[str]:
    """
    Cloud Run(Compute Engine) 환경 및 로컬 개발 환경 모두에서 안전하게 동작하는 GCS Signed URL 생성 헬퍼.
    로컬 환경이 아닐 경우, IAM Service Account Credentials API를 통해 서명을 원격 생성합니다.
    """
    try:
        import datetime
        import google.auth
        from google.auth.transport import requests
        from google.cloud import storage
        
        credentials, project_id = google.auth.default()
        
        # Compute Engine / Cloud Run 자격증명일 경우 refresh를 호출해 token을 획득
        if hasattr(credentials, "refresh"):
            try:
                auth_request = requests.Request()
                credentials.refresh(auth_request)
            except Exception as refresh_err:
                logger.warning(f"구글 자격증명 갱신 실패 (로컬 환경인 경우 무시 가능): {refresh_err}")
                
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        kwargs = {
            "version": "v4",
            "expiration": datetime.timedelta(minutes=expiration_minutes),
            "method": method,
        }
        if content_type:
            kwargs["content_type"] = content_type
        if response_content_disposition:
            kwargs["response_content_disposition"] = response_content_disposition
            
        # 자격증명에 이메일과 토큰이 존재하는 경우 (Cloud Run 환경), 원격 sign API 바인딩
        if (hasattr(credentials, "service_account_email") and credentials.service_account_email and 
            hasattr(credentials, "token") and credentials.token):
            kwargs["service_account_email"] = credentials.service_account_email
            kwargs["access_token"] = credentials.token
            logger.info(f"🔑 IAM Credentials을 통한 원격 Signed URL 생성 시작 ({credentials.service_account_email})")
            
        url = blob.generate_signed_url(**kwargs)
        return url
    except Exception as e:
        logger.error(f"❌ generate_gcs_signed_url 실패: {e}")
        return None

def get_document_signed_url(document_id: str, download_name: str) -> Optional[str]:
    """
    GCS에 저장된 원본 PDF 파일의 5분 만료 임시 다운로드 서명 링크(Signed URL)를 생성합니다.
    로컬 모드인 경우 None을 반환합니다.
    """
    if settings.USE_LOCAL_STORAGE:
        return None

    try:
        from urllib.parse import quote
        
        # RFC 5987 표준 한글 파일명 헤더 세팅 주입
        encoded_filename = quote(download_name)
        content_disposition = f"attachment; filename=\"document.pdf\"; filename*=UTF-8''{encoded_filename}"
        
        url = generate_gcs_signed_url(
            bucket_name=settings.GCS_BUCKET_NAME,
            blob_name=f"{document_id}/original.pdf",
            method="GET",
            expiration_minutes=5,
            content_type="application/pdf",
            response_content_disposition=content_disposition
        )
        return url
    except Exception as e:
        logger.error(f"❌ GCS 다운로드용 Signed URL 생성 실패: {e}")
        return None

def update_document_metadata(document_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    특정 문서의 메타데이터를 업데이트합니다.
    """
    meta = get_document(document_id)
    if meta is None:
        return None

    meta.update(updates)
    
    # 제조사명이 있을 경우 자동 표준 영문 대문자 정규화 강제 적용
    if "manufacturer" in meta:
        from app.services.pdf_service import normalize_manufacturer
        meta["manufacturer"] = normalize_manufacturer(meta["manufacturer"])
    
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


def migrate_legacy_manufacturers() -> int:
    """
    기존에 등록되어 있던 모든 문서들을 전수 조사하여,
    비표준(한글, 소문자 등) 제조사명을 표준 영문 대문자("MITSUBISHI", "FANUC" 등)로
    일괄 정규화 마이그레이션합니다.
    """
    from app.services.pdf_service import normalize_manufacturer
    logger.info("🔄 기존 문서 제조사명 정규화 마이그레이션 시작...")
    
    docs = get_all_documents()
    migrated_count = 0
    
    for doc in docs:
        doc_id = doc.get("document_id")
        orig_mfg = doc.get("manufacturer")
        
        if doc_id and orig_mfg:
            norm_mfg = normalize_manufacturer(orig_mfg)
            if norm_mfg != orig_mfg:
                logger.info(f"  [Migration] {doc.get('filename')}: '{orig_mfg}' ➔ '{norm_mfg}'")
                update_document_metadata(doc_id, {"manufacturer": norm_mfg})
                migrated_count += 1
                
    logger.info(f"✅ 제조사명 정규화 마이그레이션 완료 (총 {migrated_count}건 변환됨)")
    return migrated_count

