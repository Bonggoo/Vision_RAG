import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
import uuid
from fastapi import UploadFile

import os
import json
import hashlib
from datetime import datetime
from app.config import settings
from app.utils.logger import logger
from app.exceptions import EmptyFileError, DuplicateDocumentError
from app.services import metadata_service


def normalize_manufacturer(name: Optional[str]) -> Optional[str]:
    """
    제조사명을 영어 대문자 표준형으로 정규화합니다.
    """
    if not name:
        return None
        
    cleaned = name.strip().lower()
    
    # 1. 미쯔비시 / 미쓰비시
    if "미쯔비시" in cleaned or "미쓰비시" in cleaned or "mitsubishi" in cleaned:
        return "MITSUBISHI"
        
    # 2. 화낙 / 파낙
    if "화낙" in cleaned or "fanuc" in cleaned or "파낙" in cleaned:
        return "FANUC"
        
    # 3. 키엔스
    if "키엔스" in cleaned or "keyence" in cleaned:
        return "KEYENCE"
        
    # 4. 야스카와
    if "야스카와" in cleaned or "yaskawa" in cleaned:
        return "YASKAWA"
        
    # 5. 페스토
    if "페스토" in cleaned or "festo" in cleaned:
        return "FESTO"
        
    # 6. 오므론
    if "오므론" in cleaned or "omron" in cleaned:
        return "OMRON"
        
    # 7. 코스모
    if "코스모" in cleaned or "cosmo" in cleaned:
        return "COSMO"
        
    # 8. 오토닉스
    if "오토닉스" in cleaned or "autonics" in cleaned:
        return "AUTONICS"
        
    # 9. 로보스타
    if "로보스타" in cleaned or "robostar" in cleaned:
        return "ROBOSTAR"
        
    # 10. 유니펄스
    if "유니펄스" in cleaned or "unipulse" in cleaned:
        return "UNIPULSE"
        
    # 11. 세텍
    if "세텍" in cleaned or "setech" in cleaned:
        return "SETECH"
        
    # 12. 레디언큐바이오
    if "레디언큐바이오" in cleaned or "radionqubio" in cleaned:
        return "RADIONQUBIO"
        
    # 13. LS
    if "ls" in cleaned or "엘에스" in cleaned:
        return "LS"
        
    # 14. 지멘스
    if "지멘스" in cleaned or "siemens" in cleaned:
        return "SIEMENS"
        
    # 15. LG
    if "lg" in cleaned or "엘지" in cleaned:
        return "LG"
        
    # 💡 1차 하드코딩 맵에 걸리지 않고 한글이 포함된 단어일 경우 Gemini LLM 동적 영문화 폴백 적용!
    import re
    if re.search(r"[ㄱ-ㅎㅏ-ㅣ가-힣]", name):
        try:
            from app.services.agent_service import normalize_manufacturer_with_llm
            logger.info(f"🔮 사전에 없는 제조사 '{name}' ➔ Gemini 동적 영문화 판별 실행...")
            llm_result = normalize_manufacturer_with_llm(name)
            logger.info(f"  ➔ Gemini 판별 결과: '{name}' ➔ '{llm_result}'")
            return llm_result
        except Exception as e:
            logger.error(f"❌ Gemini 동적 정규화 실패: {e}")
            
    return name.strip().upper()


def is_toc_meaningful(toc: List[Dict[str, Any]], total_pages: int) -> bool:
    """
    추출된 목차(ToC)의 품질이 충분한지 검사합니다.
    """
    if not toc:
        return False
        
    # 기준 1: 페이지 수 대비 항목이 너무 적은 경우 (예: 100페이지당 1개 미만)
    if total_pages > 100 and len(toc) < (total_pages / 100):
        return False
        
    has_sublevels = any(item["level"] > 1 for item in toc)
    if not has_sublevels and len(toc) < 20:
        return False
        
    return True


async def process_document_upload(file: UploadFile, owner_email: str = "") -> Dict[str, Any]:
    """
    업로드된 PDF 파일을 저장하고, 3단계 ToC 추출 전략(A,B,C)을 수행한 후 메타데이터를 반환합니다.
    ToC가 부실한 경우 자동으로 Vision 기반 세부 목차 보강을 실행합니다.
    """
    content = await file.read()
    
    # 1. 빈 파일(0바이트) 검증
    if len(content) == 0:
        raise EmptyFileError()
        
    # 2. SHA-256 해시 계산 및 중복 검증
    file_hash = hashlib.sha256(content).hexdigest()
    existing_docs = metadata_service.get_all_documents(owner_email=owner_email if owner_email else None)
    for doc_meta in existing_docs:
        if doc_meta.get("file_hash") == file_hash:
            raise DuplicateDocumentError(doc_meta["filename"])

    doc_id = uuid.uuid4()
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, str(doc_id))
    os.makedirs(doc_dir, exist_ok=True)
    
    file_path = os.path.join(doc_dir, "original.pdf")
    with open(file_path, "wb") as f:
        f.write(content)
        
    doc = fitz.open(file_path)
    total_pages = doc.page_count
    
    # 1. ToC 추출 시도 — PDF 북마크
    raw_toc = extract_toc(doc)
    
    if is_toc_meaningful(raw_toc, total_pages):
        # Case A-1: 북마크 ToC가 충분히 상세 → 그대로 사용
        toc = raw_toc
        status = "indexed"
        print(f"📋 Case A-1: 북마크 ToC 사용 ({len(toc)}개 항목)")
    elif raw_toc:
        # Case A-2: 북마크 존재하지만 부실 → 목차 페이지 탐색
        print(f"📋 Case A-2: 북마크 ToC 부실 ({len(raw_toc)}개), 목차 페이지 탐색 시작...")
        from app.services.agent_service import find_and_extract_toc
        toc = find_and_extract_toc(doc, total_pages)
        if not toc:
            # 목차 페이지를 못 찾으면 북마크라도 사용
            toc = raw_toc
            print(f"  ⚠️ 목차 페이지 미발견, 북마크 ToC 유지 ({len(raw_toc)}개)")
        status = "indexed"
    else:
        # 북마크 없음
        toc = []
        status = "indexed"
    
    if not toc:
        from app.services.agent_service import extract_toc_with_gemini
        scanned = is_scanned_pdf(doc)
        
        if scanned and total_pages > 50:
            # Case C: 스캔본 & 50페이지 초과 -> 사용자 입력 요청
            status = "toc_required"
            print(f"📋 Case C: 스캔본 대용량 → 사용자 ToC 범위 입력 필요")
        else:
            # Case B: 텍스트 있음 or (스캔본 & 50페이지 이하)
            print(f"📋 Case B: Gemini 앞부분 스캔으로 ToC 추출...")
            extract_pages = min(15, total_pages)
            mini_pdf_bytes = extract_pages_as_pdf(doc, 0, extract_pages - 1)
            toc = extract_toc_with_gemini(mini_pdf_bytes)
        
    doc.close()
    
    # 3. AI 기반 자동 분류 및 제목 추출
    classification = await _extract_document_classification(file_path, file.filename)
    
    metadata = {
        "document_id": str(doc_id),
        "filename": classification["title"],
        "original_filename": file.filename,
        "total_pages": total_pages,
        "toc": toc,
        "uploaded_at": datetime.now().isoformat(),
        "status": status,
        "file_hash": file_hash,
        "manufacturer": classification.get("manufacturer"),
        "model_series": classification.get("model_series"),
        "doc_type": classification.get("doc_type"),
        "owner_email": owner_email,
    }
    
    with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
        
    # GCS 업로드 추가
    if settings.USE_LOCAL_STORAGE:
        logger.info(f"📁 로컬 스토리지 모드: GCS 업로드를 건너뜁니다. (ID: {doc_id})")
    else:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(settings.GCS_BUCKET_NAME)
            
            blob_pdf = bucket.blob(f"{doc_id}/original.pdf")
            blob_pdf.upload_from_string(content, content_type="application/pdf")
            
            blob_meta = bucket.blob(f"{doc_id}/metadata.json")
            blob_meta.upload_from_string(json.dumps(metadata, ensure_ascii=False, indent=2), content_type="application/json")
            logger.info(f"✅ GCS 업로드 성공: {doc_id}")
        except Exception as e:
            logger.error(f"❌ GCS 업로드 실패: {e}")
        
    return metadata


async def _extract_document_classification(pdf_path: str, fallback: str) -> dict:
    """
    PDF에서 메타데이터(제조사, 모델, 문서유형, 제목)를 자동 추출 및 분류합니다.
    """
    import re
    from app.services.agent_service import extract_document_metadata_with_gemini

    result = {
        "title": None,
        "manufacturer": None,
        "model_series": None,
        "doc_type": None
    }

    # 노이즈 패턴: 저작권, 주소, URL, 날짜, 전화번호, 숫자만 있는 줄 등
    _noise_patterns = re.compile(
        r"^[\d\-\.]+$"              # 숫자만
        r"|^page"                   # 페이지
        r"|^[A-Z]-\d"              # A-1 형식
        r"|^\d{4}년"               # 날짜
        r"|©|all rights reserved"  # 저작권
        r"|www\.|http"             # URL
        r"|^\+?\d[\d\s\-]{6,}"    # 전화번호
        r"|straße|street|road"     # 주소
        r"|^\d{4,}$"               # 긴 숫자 코드
        r"|원본.*번역|translation"  # 번역 관련
        r"|festo\s+se|co\.\s*kg"   # 특정 회사명(제목 아닌 주소/저작권 라인)
        , re.IGNORECASE
    )

    try:
        doc = fitz.open(pdf_path)
        
        # 1단계: Gemini Vision을 이용해 표지 페이지 분석하여 메타데이터 추출
        try:
            if doc.page_count > 0:
                first_page_pdf = extract_pages_as_pdf(doc, 0, 0)
                gemini_meta = await extract_document_metadata_with_gemini(first_page_pdf)
                if gemini_meta:
                    result["title"] = gemini_meta.get("title")
                    result["manufacturer"] = gemini_meta.get("manufacturer")
                    result["model_series"] = gemini_meta.get("model_series")
                    result["doc_type"] = gemini_meta.get("doc_type")
                    logger.info(f"✨ Gemini Vision 기반 분류 성공: {result}")
        except Exception as gemini_err:
            logger.error(f"⚠️ Gemini 기반 분류 오류: {gemini_err}")

        # 2단계: Gemini가 실패했거나 특정 필드가 없는 경우, 기존 로컬 룰 적용하여 제목 채우기
        if not result["title"]:
            # PDF 메타데이터에서 title 확인
            pdf_meta = doc.metadata or {}
            pdf_title = (pdf_meta.get("title") or "").strip()
            if pdf_title and len(pdf_title) > 5 and pdf_title != fallback:
                result["title"] = pdf_title
            
            # 첫 페이지 텍스트에서 제목 조합
            if not result["title"] and doc.page_count > 0:
                first_page = doc[0]
                text = first_page.get_text().strip()
                if text:
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    meaningful = []
                    for l in lines[:20]:
                        if len(l) > 2 and not _noise_patterns.search(l):
                            meaningful.append(l)
                    
                    if meaningful:
                        model_pattern = re.compile(r"^[A-Z][A-Z0-9\-]{2,}$")
                        generic_terms = {"PLC", "CPU", "HMI", "USB", "LED", "LCD", "FAQ", "PDF"}
                        model_name = None
                        doc_type_extracted = None
                        
                        for l in meaningful:
                            if model_name is None and model_pattern.match(l) and l not in generic_terms:
                                model_name = l
                            if doc_type_extracted is None and re.search(
                                r"매뉴얼|사용.*설명서|설명서|가이드|manual|guide|instruction|operating",
                                l, re.IGNORECASE
                            ):
                                doc_type_extracted = l
                        
                        if model_name is None:
                            model_candidates = []
                            for l in meaningful:
                                if re.search(r"[A-Z][A-Za-z]*[\-]?[A-Z0-9]{2,}", l):
                                    model_candidates.append(l)
                            if model_candidates:
                                model_name = max(model_candidates, key=len)
                        
                        if model_name and doc_type_extracted and model_name != doc_type_extracted:
                            result["title"] = f"{model_name} {doc_type_extracted}"
                        elif model_name:
                            result["title"] = model_name
                        elif doc_type_extracted:
                            result["title"] = doc_type_extracted
                        else:
                            result["title"] = meaningful[0]
            
            # 최종 fallback: 파일명 사용
            if not result["title"]:
                name = fallback
                if name.lower().endswith(".pdf"):
                    name = name[:-4]
                result["title"] = name

        doc.close()
    except Exception as e:
        logger.error(f"⚠️ 문서 분류 및 제목 추출 실패: {e}")
        # 예외 발생 시 최종 fallback
        name = fallback
        if name.lower().endswith(".pdf"):
            name = name[:-4]
        result["title"] = name

    # 정규화: null/미분류 값 통일 및 제조사 표준 영문화 적용
    result["manufacturer"] = normalize_manufacturer(result["manufacturer"])
    
    if result["model_series"] == "null" or result["model_series"] == "":
        result["model_series"] = None
    if result["doc_type"] == "null" or result["doc_type"] == "":
        result["doc_type"] = None

    return result

def extract_toc(doc: fitz.Document) -> List[Dict[str, Any]]:
    """
    PDF 문서에서 북마크를 기반으로 목차(ToC)를 추출합니다.
    결과: [{"level": 1, "title": "...", "page": 1}, ...]
    """
    toc_raw = doc.get_toc()
    toc = []
    for item in toc_raw:
        if len(item) >= 3:
            toc.append({
                "level": item[0],
                "title": item[1],
                "page": item[2]
            })
    return toc

def is_scanned_pdf(doc: fitz.Document) -> bool:
    """
    문서의 텍스트가 거의 없는지(스캔된 문서인지) 확인합니다.
    초반 3페이지만 검사합니다.
    """
    check_pages = min(3, doc.page_count)
    total_text = ""
    for i in range(check_pages):
        page = doc[i]
        total_text += page.get_text()
    
    # 텍스트가 50글자 미만이면 스캔 문서로 간주
    return len(total_text.strip()) < 50

def extract_pages_as_pdf(doc: fitz.Document, start_page: int, end_page: int) -> bytes:
    """
    특정 페이지 범위를 새로운 미니 PDF로 추출합니다.
    page_num은 0-indexed로 가정하거나 필요시 변환합니다.
    """
    # 안전장치: 범위를 문서 크기 이내로 제한
    start_page = max(0, start_page)
    end_page = min(doc.page_count - 1, end_page)
    
    mini_doc = fitz.open()
    mini_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
    pdf_bytes = mini_doc.tobytes()
    mini_doc.close()
    return pdf_bytes

def render_page_thumbnail(doc: fitz.Document, page_num: int, dpi: int = 72) -> bytes:
    """
    특정 페이지의 썸네일 PNG를 생성합니다. (프론트엔드 표시용)
    """
    if page_num < 0 or page_num >= doc.page_count:
        raise ValueError("Invalid page number")
        
    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")

def render_page_image(doc: fitz.Document, page_num: int, dpi: int = 200) -> bytes:
    """
    특정 페이지의 고해상도 확대 PNG를 생성합니다.
    """
    return render_page_thumbnail(doc, page_num, dpi=dpi)
