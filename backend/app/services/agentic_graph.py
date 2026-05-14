"""
Agentic Search 파이프라인.

2단계 추론(Two-Phase Reasoning)을 활용하여 정확한 페이지를 탐색합니다.
Phase 1: ToC 기반 섹션 특정 → 해당 섹션 첫 수 페이지를 Vision으로 세부 목차 읽기
Phase 2: 세부 목차 기반 정확한 페이지 특정 → Vision 분석 → 답변 스트리밍
"""
import base64
import json
import fitz  # PyMuPDF
from typing import AsyncGenerator
from app.services.metadata_service import get_document, get_document_path
from app.services.agent_service import reason_target_pages, analyze_pages_with_vision, _create_llm, _clean_json_response
from app.services.pdf_service import extract_pages_as_pdf, render_page_thumbnail
from langchain_core.messages import HumanMessage


def _sse_event(event_type: str, **kwargs) -> str:
    """SSE 이벤트 문자열을 생성합니다."""
    data = {"type": event_type, **kwargs}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _find_section_page_range(toc: list[dict], target_page: int, total_pages: int) -> tuple[int, int]:
    """
    ToC에서 target_page가 속한 섹션의 시작~끝 페이지를 반환합니다.
    다음 섹션의 시작 직전까지를 범위로 잡습니다.
    """
    pages = sorted(set(entry.get("page", 1) for entry in toc))
    start = target_page
    end = total_pages

    for i, p in enumerate(pages):
        if p <= target_page:
            start = p
            if i + 1 < len(pages):
                end = pages[i + 1] - 1
            else:
                end = total_pages
    return start, end


def _refine_pages_with_vision(
    doc: fitz.Document,
    section_start: int,
    section_end: int,
    question: str,
) -> dict:
    """
    Phase 2: 섹션의 앞부분 (목차/개요 페이지)을 Vision으로 읽어
    정확한 타겟 페이지를 추론합니다.
    
    섹션 시작 후 최대 8페이지를 스캔하여 세부 목차를 파악합니다.
    """
    llm = _create_llm()
    
    # 섹션 앞부분 최대 8페이지를 Vision으로 스캔
    scan_start = section_start - 1  # 0-indexed
    scan_end = min(scan_start + 7, section_end - 1, doc.page_count - 1)
    
    mini_pdf = extract_pages_as_pdf(doc, scan_start, scan_end)
    pdf_base64 = base64.b64encode(mini_pdf).decode("utf-8")
    
    # 스캔 페이지 매핑 정보 생성
    page_mapping = ", ".join(
        f"PDF {i+1}번째 페이지 = 절대 페이지 {scan_start + i + 1}"
        for i in range(scan_end - scan_start + 1)
    )
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
첨부된 PDF 페이지들은 전체 매뉴얼의 한 섹션 앞부분입니다.
이 페이지들의 목차, 제목, 본문을 분석하여 아래 질문에 답하기 위해 참조해야 할 **정확한 절대 페이지 번호**를 추론하세요.

질문: "{question}"

현재 섹션의 절대 페이지 범위: {section_start} ~ {section_end}
첨부 페이지 매핑: {page_mapping}

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "reasoning": "세부 목차를 분석한 추론 과정을 한국어로 상세히 설명",
    "target_pages": [절대_페이지_번호1, 절대_페이지_번호2, ...],
    "section_title": "관련 섹션의 정확한 제목"
}}

⚠️ 중요 규칙:
- target_pages에는 반드시 **절대 페이지 번호 (정수)**를 사용하세요.
- 매뉴얼 내부 표기(예: "3-32", "5-61")가 아닌, PDF 전체에서의 순서 번호입니다.
- 예: 매뉴얼 내부 "3-32 페이지"가 이 섹션의 시작(절대 {section_start})에서 32번째라면, 절대 번호는 {section_start} + 31 = {section_start + 31} 입니다.
- 매뉴얼에 "X-Y" 형식 페이지 번호가 있으면, Y값에 해당 섹션 시작 절대 페이지를 더해서 계산하세요.
  계산식: 절대 페이지 = {section_start} + (Y - 1)
- 타겟 페이지는 최소 2개, 최대 8개로 설정합니다.
- 연속된 페이지라면 사이 페이지도 포함합니다.
"""
    
    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
    ])
    
    try:
        response = llm.invoke([message])
        content = _clean_json_response(response.content)
        result = json.loads(content)
        
        # 페이지 번호 정규화: 문자열이나 잘못된 값 필터링
        raw_pages = result.get("target_pages", [])
        normalized = []
        for p in raw_pages:
            if isinstance(p, int):
                normalized.append(p)
            elif isinstance(p, str):
                # "3-32" 같은 형식 처리: Y값에 섹션 시작 오프셋 적용
                import re
                match = re.match(r"(\d+)-(\d+)", p)
                if match:
                    y = int(match.group(2))
                    normalized.append(section_start + y - 1)
                elif p.isdigit():
                    normalized.append(int(p))
        
        # 범위 검증
        normalized = [p for p in normalized if section_start <= p <= section_end]
        if not normalized:
            # 실패 시 섹션 앞부분으로 폴백
            normalized = list(range(section_start, min(section_start + 5, section_end + 1)))
        
        result["target_pages"] = normalized[:8]
        return result
    except Exception as e:
        print(f"Vision Refine Error: {e}")
        # 실패 시 섹션 앞부분 5페이지를 기본값으로
        fallback_pages = list(range(section_start, min(section_start + 5, section_end + 1)))
        return {
            "reasoning": f"세부 추론 실패, 섹션 앞부분 탐색: {str(e)}",
            "target_pages": fallback_pages,
            "section_title": "알 수 없음"
        }


async def run_agentic_pipeline(
    document_id: str,
    question: str,
    chat_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    2단계 Agentic Search 파이프라인을 실행합니다.
    
    Phase 1: ToC 기반 대략적 섹션 특정
    Phase 2: 섹션 앞부분 Vision 스캔 → 정확한 페이지 특정
    Phase 3: 타겟 페이지 미니 PDF 추출 + Vision 분석 → 답변 스트리밍
    """
    
    # ─── Step 1: 문서 검증 및 ToC 로드 ───
    meta = get_document(document_id)
    if meta is None:
        yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {document_id}")
        yield _sse_event("done")
        return
    
    pdf_path = get_document_path(document_id)
    if pdf_path is None:
        yield _sse_event("error", content="PDF 파일을 찾을 수 없습니다.")
        yield _sse_event("done")
        return
    
    toc = meta.get("toc", [])
    if not toc:
        yield _sse_event("error", content="목차(ToC)가 없는 문서입니다. 먼저 ToC를 추출해주세요.")
        yield _sse_event("done")
        return
    
    yield _sse_event("reasoning", content=f"'{meta.get('filename', '')}' 문서의 목차를 로드했습니다. ({len(toc)}개 항목)")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
    except Exception as e:
        yield _sse_event("error", content=f"PDF 파일 열기 실패: {str(e)}")
        yield _sse_event("done")
        return
    
    # ─── Step 2: Phase 1 — ToC 기반 대략적 섹션 특정 ───
    yield _sse_event("reasoning", content="[Phase 1] 목차를 분석하여 관련 섹션을 찾고 있습니다...")
    
    phase1_result = reason_target_pages(toc, question)
    coarse_pages = phase1_result.get("target_pages", [1])
    coarse_title = phase1_result.get("section_title", "")
    coarse_reasoning = phase1_result.get("reasoning", "")
    
    # 대략적 페이지에서 섹션 범위를 계산
    primary_page = coarse_pages[0] if coarse_pages else 1
    section_start, section_end = _find_section_page_range(toc, primary_page, total_pages)
    
    yield _sse_event(
        "reasoning",
        content=f"[Phase 1] '{coarse_title}' 섹션 특정 완료 (p.{section_start}~{section_end})\n{coarse_reasoning}"
    )
    
    # ─── Step 3: Phase 2 — Vision으로 세부 페이지 특정 ───
    yield _sse_event("reasoning", content=f"[Phase 2] 섹션 앞부분(p.{section_start}~{min(section_start+7, section_end)})을 Vision으로 스캔하여 정확한 페이지를 찾고 있습니다...")
    
    phase2_result = _refine_pages_with_vision(doc, section_start, section_end, question)
    target_pages = phase2_result.get("target_pages", coarse_pages)
    refined_title = phase2_result.get("section_title", coarse_title)
    refined_reasoning = phase2_result.get("reasoning", "")
    
    yield _sse_event(
        "reasoning",
        content=f"[Phase 2] '{refined_title}' → 타겟 페이지 {target_pages}\n{refined_reasoning}"
    )
    
    # ─── Step 4: 미니 PDF 추출 + 참조 이미지 생성 ───
    yield _sse_event("reasoning", content=f"페이지 {target_pages}에서 미니 PDF를 추출하고 있습니다...")
    
    try:
        valid_pages = [p - 1 for p in target_pages if 1 <= p <= total_pages]
        if not valid_pages:
            valid_pages = [0]
        
        start_page = min(valid_pages)
        end_page = max(valid_pages)
        
        mini_pdf_bytes = extract_pages_as_pdf(doc, start_page, end_page)
        
        for page_idx in valid_pages:
            try:
                png_bytes = render_page_thumbnail(doc, page_idx, dpi=150)
                image_base64 = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"
                yield _sse_event(
                    "reference",
                    page_number=page_idx + 1,
                    image_base64=image_base64,
                )
            except Exception as e:
                print(f"Thumbnail generation error for page {page_idx}: {e}")
        
        doc.close()
        
    except Exception as e:
        doc.close()
        yield _sse_event("error", content=f"PDF 처리 중 오류: {str(e)}")
        yield _sse_event("done")
        return
    
    # ─── Step 5: Vision LLM 분석 (스트리밍) ───
    yield _sse_event("reasoning", content="Gemini Vision으로 페이지를 분석하고 있습니다...")
    
    try:
        async for chunk in analyze_pages_with_vision(mini_pdf_bytes, question, chat_history=chat_history):
            yield _sse_event("answer", content=chunk)
    except Exception as e:
        yield _sse_event("error", content=f"Vision 분석 중 오류: {str(e)}")
    
    yield _sse_event("done")
