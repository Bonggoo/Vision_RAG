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
    
    # 1. ToC 추출 시도 (Case A)
    raw_toc = extract_toc(doc)
    
    # 품질 검사 (Case A-1 판별)
    if is_toc_meaningful(raw_toc, total_pages):
        toc = raw_toc
        status = "indexed"
    else:
        toc = []
        status = "indexed" # 추후 Gemini 추출 완료 시 상태
    
    if not toc:
        from app.services.agent_service import extract_toc_with_gemini
        # 북마크 없음
        scanned = is_scanned_pdf(doc)
        
        if scanned and total_pages > 50:
            # Case C: 스캔본 & 50페이지 초과 -> 사용자 입력 요청
            status = "toc_required"
        else:
            # Case B: 텍스트 있음 or (스캔본 & 50페이지 이하)
            # 앞부분(최대 15페이지) 미니 PDF 추출
            extract_pages = min(15, total_pages)
            mini_pdf_bytes = extract_pages_as_pdf(doc, 0, extract_pages - 1)
            toc = extract_toc_with_gemini(mini_pdf_bytes)
            
    doc.close()
    
    metadata = {
        "document_id": str(doc_id),
        "filename": file.filename,
        "total_pages": total_pages,
        "toc": toc,
        "uploaded_at": datetime.now().isoformat(),
        "status": status
    }
    
    with open(os.path.join(doc_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
        
    return metadata

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
