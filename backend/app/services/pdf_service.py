import fitz  # PyMuPDF
from typing import List, Dict, Any
import uuid
from fastapi import UploadFile

import os
import json
from datetime import datetime
from app.config import settings

def is_toc_meaningful(toc: List[Dict[str, Any]], total_pages: int) -> bool:
    """
    추출된 목차(ToC)의 품질이 충분한지 검사합니다.
    """
    if not toc:
        return False
        
    # 기준 1: 페이지 수 대비 항목이 너무 적은 경우 (예: 100페이지당 1개 미만)
    if total_pages > 100 and len(toc) < (total_pages / 100):
        return False
        
    # 기준 2: 모든 항목이 Level 1이고 항목이 너무 적은 경우 (단순 파트 구분)
    has_sublevels = any(item["level"] > 1 for item in toc)
    if not has_sublevels and len(toc) < 20:
        return False
        
    return True

async def process_document_upload(file: UploadFile) -> Dict[str, Any]:
    """
    업로드된 PDF 파일을 저장하고, 3단계 ToC 추출 전략(A,B,C)을 수행한 후 메타데이터를 반환합니다.
    ToC가 부실한 경우 자동으로 Vision 기반 세부 목차 보강을 실행합니다.
    """
    doc_id = uuid.uuid4()
    doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, str(doc_id))
    os.makedirs(doc_dir, exist_ok=True)
    
    file_path = os.path.join(doc_dir, "original.pdf")
    content = await file.read()
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
    
    # 파일명 자동 추출: PDF 메타데이터 또는 첫 페이지에서 제목 추출
    auto_title = _extract_document_title(file_path, file.filename)
    
    metadata = {
        "document_id": str(doc_id),
        "filename": auto_title,
        "original_filename": file.filename,
        "total_pages": total_pages,
        "toc": toc,
        "uploaded_at": datetime.now().isoformat(),
        "status": status
    }
    
    with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
        
    return metadata


def _extract_document_title(pdf_path: str, fallback: str) -> str:
    """
    PDF에서 문서 제목을 자동 추출합니다.
    
    우선순위:
    1. PDF 메타데이터의 title 필드
    2. 첫 페이지 텍스트에서 모델명 + 문서 유형 조합
    3. 원본 파일명 (fallback)
    """
    import re
    
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
        
        # 1단계: PDF 메타데이터에서 title 확인
        pdf_meta = doc.metadata or {}
        pdf_title = (pdf_meta.get("title") or "").strip()
        
        # 의미 있는 제목인지 검사 (너무 짧거나 파일명과 같으면 스킵)
        if pdf_title and len(pdf_title) > 5 and pdf_title != fallback:
            doc.close()
            return pdf_title
        
        # 2단계: 첫 페이지 텍스트에서 제목 조합
        if doc.page_count > 0:
            first_page = doc[0]
            text = first_page.get_text().strip()
            
            if text:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                
                # 노이즈 라인 필터링
                meaningful = []
                for l in lines[:20]:
                    if len(l) > 2 and not _noise_patterns.search(l):
                        meaningful.append(l)
                
                if meaningful:
                    # 모델명 패턴: 대문자 영문 + 숫자/하이픈 조합 (예: HPPF, QD77MS, MELSEC-Q)
                    model_pattern = re.compile(r"^[A-Z][A-Z0-9\-]{2,}$")
                    # 일반 약어 제외 패턴 (PLC, CPU 등 너무 범용적인 단어)
                    generic_terms = {"PLC", "CPU", "HMI", "USB", "LED", "LCD", "FAQ", "PDF"}
                    model_name = None
                    doc_type = None
                    
                    for l in meaningful:
                        # 모델명: 대문자+숫자만으로 구성된 줄 (범용 약어 제외)
                        if model_name is None and model_pattern.match(l) and l not in generic_terms:
                            model_name = l
                        
                        # 문서 유형: 매뉴얼, 사용 설명서, 가이드 등
                        if doc_type is None and re.search(
                            r"매뉴얼|사용.*설명서|설명서|가이드|manual|guide|instruction|operating",
                            l, re.IGNORECASE
                        ):
                            doc_type = l
                    
                    # 모델명을 못 찾았으면 완화된 패턴으로 재탐색
                    # (영문+숫자 조합이 포함된 줄 중 가장 긴 줄 = 가장 설명이 풍부한 줄)
                    if model_name is None:
                        model_candidates = []
                        for l in meaningful:
                            if re.search(r"[A-Z][A-Za-z]*[\-]?[A-Z0-9]{2,}", l):
                                model_candidates.append(l)
                        if model_candidates:
                            model_name = max(model_candidates, key=len)
                    
                    # 제목 조합
                    if model_name and doc_type and model_name != doc_type:
                        title = f"{model_name} {doc_type}"
                        if len(title) < 80:
                            doc.close()
                            return title
                    
                    if model_name:
                        doc.close()
                        return model_name
                    
                    if doc_type:
                        doc.close()
                        return doc_type
                    
                    # 둘 다 없으면 첫 번째 의미 있는 줄 사용
                    doc.close()
                    return meaningful[0]
        
        doc.close()
    except Exception as e:
        print(f"  ⚠️ 문서 제목 자동 추출 실패: {e}")
    
    # fallback: 원본 파일명 (.pdf 제거)
    name = fallback
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return name

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
