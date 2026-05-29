"""
Agentic Search 파이프라인.

3단계 하이브리드 추론(텍스트 + PDF)을 활용하여 정확한 페이지를 탐색합니다.
Phase 0+1: 문서 선택 + ToC 기반 섹션 특정 (Flash-Lite)
Phase 2: 섹션 전체 텍스트 추출 → 정확한 타겟 페이지 특정 (Flash-Lite)
Phase 3: 타겟 페이지 미니 PDF 분석 → 답변 스트리밍 (Flash-Lite)
"""
import base64
import json
import fitz  # PyMuPDF
from typing import AsyncGenerator
from app.services.metadata_service import get_document, get_document_path, get_all_documents
from app.services.agent_service import analyze_pages_with_vision, _create_flash_llm, _clean_json_response
from app.services.pdf_service import extract_pages_as_pdf, render_page_thumbnail
from app.utils.logger import logger
from langchain_core.messages import HumanMessage


def _sse_event(event_type: str, **kwargs) -> str:
    """SSE 이벤트 문자열을 생성합니다."""
    data = {"type": event_type, **kwargs}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalize_page(page_value) -> int:
    """
    ToC의 페이지 값을 정수로 정규화합니다.
    
    지원 형식:
    - int: 그대로 반환
    - "1-1" (챕터-페이지): 숫자만 추출 후 조합 (fallback: 마지막 숫자)
    - "32": 문자열 정수
    - 기타: 1 반환
    """
    if isinstance(page_value, int):
        return page_value
    if isinstance(page_value, float):
        return int(page_value)
    if isinstance(page_value, str):
        page_value = page_value.strip()
        # 순수 숫자
        if page_value.isdigit():
            return int(page_value)
        # "3-32" 형식: 하이픈 뒤 숫자 사용 (섹션 내 상대 페이지)
        import re
        match = re.match(r"(\d+)[^\d]+(\d+)", page_value)
        if match:
            return int(match.group(2))
    return 1


def _find_section_page_range(toc: list[dict], target_pages: list[int], total_pages: int) -> tuple[int, int]:
    """
    Phase 2 텍스트 검색 범위를 결정합니다.
    
    - start: target_pages 이전의 가장 가까운 ToC 항목 (섹션 시작점)
    - end: start + 199 (최대 200페이지 범위로 넉넉하게 탐색)
    
    ToC 하위 항목 경계에서 끊지 않습니다.
    알람코드처럼 하나의 큰 섹션 안에 수십 페이지에 걸친 상세 목록이 있는 경우,
    다음 ToC 항목에서 자르면 뒤쪽 내용을 놓치기 때문입니다.
    """
    if not target_pages:
        return 1, min(200, total_pages)
        
    pages = sorted(set(_normalize_page(entry.get("page", 1)) for entry in toc))
    min_target = min(target_pages)
    
    # 섹션 시작: min_target 이하에서 가장 가까운 ToC 항목
    start = min_target
    for p in reversed(pages):
        if p <= min_target:
            start = p
            break
    
    # 섹션 끝: start로부터 최대 200페이지 (넉넉하게 탐색)
    end = min(start + 199, total_pages)
    return start, end


def _refine_pages_with_text(
    doc: fitz.Document,
    section_start: int,
    section_end: int,
    question: str,
) -> dict:
    """
    Phase 2: 섹션 내의 전체 텍스트를 추출하여 경량 LLM(Flash-Lite)에게 분석시키고,
    질문에 답변하기 위한 정확한 타겟 페이지를 추론합니다.
    """
    llm = _create_flash_llm()
    logger.info(f"🔍 [Phase 2] 정밀 텍스트 탐색 시작: p.{section_start}~{section_end}")
    
    # 전달받은 section_start ~ section_end 전체 텍스트 추출 (최대 200페이지)

    scan_end = min(section_end, section_start + 199, doc.page_count)
    
    text_content = []
    for page_idx in range(section_start - 1, scan_end):
        text = doc[page_idx].get_text()
        text_content.append(f"--- PAGE {page_idx + 1} ---\n{text}\n")
    
    full_text = "\n".join(text_content)
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 전체 매뉴얼의 특정 섹션에 포함된 텍스트입니다.
이 텍스트를 꼼꼼히 읽고 검색하여, 아래 질문에 답하기 위해 참조해야 할 **정확한 절대 페이지 번호**를 찾으세요.

질문: "{question}"

--- 섹션 텍스트 시작 ---
{full_text}
--- 섹션 텍스트 끝 ---

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "reasoning": "텍스트를 검색/분석한 추론 과정을 한국어로 간략히 설명",
    "target_pages": [절대_페이지_번호1, 절대_페이지_번호2, ...],
    "section_title": "관련 내용이 포함된 가장 정확한 섹션 또는 표의 제목"
}}

⚠️ 중요 규칙:
- target_pages에는 본문 텍스트의 '--- PAGE X ---'에 표시된 페이지 번호(정수)를 사용하세요.
- 질문의 키워드(예: 에러 번호 2050, 알람 코드, 특정 부품명)가 정확히 일치하는 페이지를 찾으세요.
- 타겟 페이지는 최소 1개, 최대 3개로 설정합니다.
- 만약 제공된 텍스트 내에 관련 내용이 없다면, 원래 섹션 시작 페이지인 [{section_start}] 를 넣으세요.
"""
    
    message = HumanMessage(content=prompt)
    
    try:
        response = llm.invoke([message])
        content = _clean_json_response(response.content)
        result = json.loads(content)
        
        # 페이지 정규화
        raw_pages = result.get("target_pages", [section_start])
        normalized = [_normalize_page(p) for p in raw_pages]
        
        # 범위 검증
        normalized = [p for p in normalized if section_start <= p <= scan_end]
        if not normalized:
            normalized = [section_start]
        
        result["target_pages"] = normalized[:3]
        return result
    except Exception as e:
        logger.error(f"❌ [Phase 2] Text Refine Error: {e}", exc_info=True)
        return {
            "reasoning": f"세부 텍스트 분석 실패, 섹션 시작 페이지로 폴백: {str(e)}",
            "target_pages": [section_start],
            "section_title": "알 수 없음"
        }



def _select_document_and_pages(
    question: str,
    documents: list[dict],
) -> dict:
    """
    Phase 0+1 통합: 문서 선택 + 타겟 페이지 추론을 1회 LLM 호출로 처리합니다.
    
    문서가 1개면 선택 없이 바로 페이지 추론만 수행합니다.
    
    Returns:
        {
            "document_id": "선택된 문서 ID",
            "target_pages": [페이지 번호들],
            "section_title": "관련 섹션 제목",
            "reasoning": "추론 과정"
        }
    """
    llm = _create_flash_llm()
    logger.info(f"🔍 [Phase 0+1] 문서 및 페이지 1차 추론 시작 (질문: {question[:50]}...)")
    
    single_doc = len(documents) == 1

    
    # 각 문서의 요약 정보 구성
    doc_summaries = []
    for i, doc in enumerate(documents):
        toc = doc.get("toc", [])
        toc_text = json.dumps(toc, ensure_ascii=False)
        # ToC가 너무 크면 잘라냄 (토큰 절약)
        if len(toc_text) > 3000:
            toc_text = json.dumps(toc[:30], ensure_ascii=False) + f" ... (총 {len(toc)}개 항목)"
        
        doc_summaries.append(
            f"[문서 {i+1}]\n"
            f"  ID: {doc['document_id']}\n"
            f"  제목: {doc.get('filename', '알 수 없음')}\n"
            f"  원본 파일명: {doc.get('original_filename', '')}\n"
            f"  페이지 수: {doc.get('total_pages', 0)}\n"
            f"  목차(ToC):\n{toc_text}"
        )
    
    docs_text = "\n\n".join(doc_summaries)
    
    if single_doc:
        select_instruction = "문서가 1개이므로 해당 문서를 사용합니다."
    else:
        select_instruction = "먼저 질문에 가장 적합한 문서를 선택하세요."
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 업로드된 문서 목록과 목차입니다:

{docs_text}

사용자의 질문: "{question}"

{select_instruction}
그리고 선택한 문서의 목차를 분석하여, 이 질문에 답하기 위해 참조해야 할 타겟 페이지를 추론하세요.

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "document_id": "선택한 문서의 ID",
    "target_pages": [시작페이지, ..., 끝페이지],
    "section_title": "관련 섹션의 제목",
    "reasoning": "문서 선택 및 페이지 추론 과정을 한국어로 간략히 설명"
}}

규칙:
- 타겟 페이지는 최소 1개, 최대 5개로 제한합니다.
- 페이지 번호는 목차에 명시된 page 값을 기준으로 합니다.
- 연속된 페이지라면 사이 페이지도 포함합니다."""
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = json.loads(_clean_json_response(response.content))
        
        # document_id 검증
        selected_id = result.get("document_id")
        found = any(d["document_id"] == selected_id for d in documents)
        if not found:
            result["document_id"] = documents[0]["document_id"]
        
        # target_pages 정규화
        raw_pages = result.get("target_pages", [1])
        result["target_pages"] = [_normalize_page(p) for p in raw_pages][:5]
        
        return result
    except Exception as e:
        logger.error(f"❌ [Phase 0+1] Document+Page Selection Error: {e}", exc_info=True)
        return {
            "document_id": documents[0]["document_id"],
            "target_pages": [1],
            "section_title": "알 수 없음",
            "reasoning": f"추론 중 오류 발생: {str(e)}"
        }


def _is_general_conversation(question: str) -> bool:
    """
    사용자의 질문이 매뉴얼 검색이 필요 없는 일반적인 인사말이나 일상 대화인지 판별합니다.
    """
    llm = _create_flash_llm()
    
    prompt = f"""사용자의 질문을 분석하여, 이 질문이 산업용 매뉴얼(기계 작동법, 알람 코드, 기술 매뉴얼 내용 등)의 검색이 필요한 **기술적 질문**인지, 
아니면 매뉴얼 검색이 필요 없는 **단순 인사말, 시스템 소개 요구, 감사 인사 또는 일상적 대화**인지 판별하세요.

사용자 질문: "{question}"

다음 형식으로만 대답하세요 (추가 텍스트나 마크다운 없이 오직 단어 하나만):
- 매뉴얼 검색이 불필요한 일상 대화/인사/잡담인 경우: "general"
- 매뉴얼에서 정보를 찾아야 하는 기술적 질문인 경우: "technical"
"""
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = _clean_json_response(response.content).strip().lower()
        return "general" in result
    except Exception as e:
        logger.error(f"Failed to classify conversation type: {e}")
        return False


async def run_agentic_pipeline(
    document_id: str | None,
    question: str,
    chat_history: list[dict] | None = None,
    image: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Agentic Search 파이프라인을 실행합니다.
    
    3단계 하이브리드 구조:
    Phase 0+1: 문서 선택 + ToC 기반 타겟 섹션 추론 (Flash-Lite, 텍스트)
    Phase 2: 섹션 전체 텍스트 분석 → 정확한 타겟 페이지 특정 (Flash-Lite, 텍스트)
    Phase 3: 타겟 페이지 미니 PDF 분석 → 답변 스트리밍 (Flash-Lite, PDF)
    """
    logger.info(f"🚀 [Pipeline] Agentic Search 파이프라인 작동 시작 (질문: '{question}')")
    
    # ─── Step -1: 이미지 분석 및 질문/문서 매칭 보강 ───
    analyzed_meta = None
    if image:
        yield _sse_event("reasoning", content="📸 업로드하신 장비 이미지를 분석하고 있습니다...")
        try:
            from app.services.agent_service import analyze_device_image_with_gemini
            analyzed_meta = await analyze_device_image_with_gemini(image)
            
            if analyzed_meta and analyzed_meta.get("confidence", 0.0) >= 0.5:
                manuf = analyzed_meta.get("manufacturer")
                model = analyzed_meta.get("model_series")
                err_code = analyzed_meta.get("error_code")
                symptom = analyzed_meta.get("symptom")
                
                info_parts = []
                if manuf: info_parts.append(f"제조사: {manuf}")
                if model: info_parts.append(f"모델: {model}")
                if err_code: info_parts.append(f"인식된 알람: {err_code}")
                if symptom: info_parts.append(f"증상: {symptom}")
                
                yield _sse_event(
                    "reasoning",
                    content="🔍 이미지 인식 성공!\n- " + "\n- ".join(info_parts)
                )
                
                # 문서 매칭: document_id가 지정되지 않은 경우, 분석된 제조사/모델과 일치하는 문서 검색
                if document_id is None:
                    all_docs = get_all_documents()
                    matched_doc = None
                    
                    # 1순위: 제조사와 모델 모두 매칭되는 문서
                    if manuf and model:
                        for d in all_docs:
                            d_manuf = str(d.get("manufacturer", "")).upper()
                            d_model = str(d.get("model_series", "")).upper()
                            if manuf.upper() in d_manuf and model.upper() in d_model:
                                matched_doc = d
                                break
                                
                    # 2순위: 모델명 매칭
                    if not matched_doc and model:
                        for d in all_docs:
                            d_model = str(d.get("model_series", "")).upper()
                            if model.upper() in d_model:
                                matched_doc = d
                                break
                                
                    # 3순위: 제조사명 매칭
                    if not matched_doc and manuf:
                        for d in all_docs:
                            d_manuf = str(d.get("manufacturer", "")).upper()
                            if manuf.upper() in d_manuf:
                                matched_doc = d
                                break
                                
                    if matched_doc:
                        document_id = matched_doc["document_id"]
                        yield _sse_event(
                            "reasoning",
                            content=f"📂 분석 정보를 기반으로 매칭된 매뉴얼을 자동으로 선택했습니다:\n- 파일명: {matched_doc.get('filename')}"
                        )
                
                # 질문 보강 (리라이팅)
                rewritten_parts = []
                if manuf: rewritten_parts.append(manuf)
                if model: rewritten_parts.append(model)
                if err_code: rewritten_parts.append(f"알람코드 {err_code}")
                if symptom: rewritten_parts.append(symptom)
                
                if rewritten_parts:
                    # 사용자 질문이 비어있거나 너무 짧으면 알람 분석 질문으로 대체
                    if len(question.strip()) < 5:
                        question = f"{' '.join(rewritten_parts)} 원인과 조치 대처법"
                    else:
                        question = f"{' '.join(rewritten_parts)} 에러 상황: {question}"
                    
                    yield _sse_event(
                        "reasoning",
                        content=f"⚙️ 질문 보강 완료: '{question}'"
                    )
            else:
                yield _sse_event("reasoning", content="⚠️ 이미지에서 명확한 장비 브랜드나 알람코드를 파악하지 못해 일반 RAG 모드로 계속합니다.")
        except Exception as e:
            logger.error(f"Error in image preprocessing: {e}")
            yield _sse_event("reasoning", content=f"⚠️ 이미지 분석 중 오류 발생, 일반 RAG 모드로 진행합니다. (오류: {e})")

    # ─── Step 0: 일상 대화 / 인사말 판별 (Early Exit) ───
    if _is_general_conversation(question):
        yield _sse_event("reasoning", content="일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다...")
        
        llm = _create_flash_llm()
        chat_prompt = f"""당신은 산업용 매뉴얼 분석 비서 'Vision RAG 에이전트'입니다.
사용자가 매뉴얼 검색과 관계없는 일반적인 인사나 일상적 대화를 건넸습니다.
친절하고 자연스럽게 인사하고, 매뉴얼 PDF를 업로드하여 질문하면 해당 매뉴얼(알람코드, 도면, 표 등)을 원본 레이아웃 그대로 분석하여 정확하게 답변할 수 있는 도구임을 알려주세요.

사용자 입력: "{question}"

친절하고 자연스럽게 한국어로 답변을 생성해 주세요.
"""
        try:
            response = await llm.ainvoke([HumanMessage(content=chat_prompt)])
            from app.services.agent_service import _extract_text_content
            answer = _extract_text_content(response.content)
            yield _sse_event("answer", content=answer)
        except Exception as e:
            logger.error(f"Error in general chatbot response: {e}")
            yield _sse_event("answer", content="안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요? 매뉴얼 PDF를 업로드하신 뒤 관련 질문(예: 특정 에러 코드나 조치 방법)을 입력해 주시면 정확히 분석하여 답변해 드리겠습니다.")
        
        yield _sse_event("done")
        return
    
    # ─── Step 0+1: 문서 선택 + 페이지 추론 (통합) ───

    if document_id is None:
        all_docs = get_all_documents()
        
        if not all_docs:
            yield _sse_event("error", content="업로드된 문서가 없습니다. 먼저 PDF 매뉴얼을 업로드해 주세요.")
            yield _sse_event("done")
            return
        
        if len(all_docs) == 1:
            yield _sse_event("reasoning", content=f"📄 '{all_docs[0].get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다...")
        else:
            yield _sse_event("reasoning", content=f"📚 {len(all_docs)}개 문서 중 적합한 문서와 페이지를 찾고 있습니다...")
        
        selection = _select_document_and_pages(question, all_docs)
        document_id = selection["document_id"]
        coarse_pages = selection["target_pages"]
        coarse_title = selection.get("section_title", "")
        coarse_reasoning = selection.get("reasoning", "")
        
        # 선택된 문서 메타 찾기
        selected_doc = next((d for d in all_docs if d["document_id"] == document_id), all_docs[0])
        yield _sse_event(
            "reasoning",
            content=f"📄 '{selected_doc.get('filename', '')}' → '{coarse_title}' (p.{coarse_pages})\n{coarse_reasoning}"
        )
    else:
        # document_id가 지정된 경우: Phase 1만 실행
        meta = get_document(document_id)
        if meta is None:
            yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {document_id}")
            yield _sse_event("done")
            return
        
        toc = meta.get("toc", [])
        yield _sse_event("reasoning", content=f"📄 '{meta.get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다...")
        
        selection = _select_document_and_pages(question, [meta])
        coarse_pages = selection["target_pages"]
        coarse_title = selection.get("section_title", "")
        coarse_reasoning = selection.get("reasoning", "")
        
        yield _sse_event(
            "reasoning",
            content=f"'{coarse_title}' 섹션 특정 완료 (p.{coarse_pages})\n{coarse_reasoning}"
        )
    
    # ─── Step 1: 문서 검증 및 PDF 열기 ───
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
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
    except Exception as e:
        logger.error(f"❌ [Pipeline] PDF 파일 열기 실패 ({pdf_path}): {e}", exc_info=True)
        yield _sse_event("error", content=f"PDF 파일 열기 실패: {str(e)}")
        yield _sse_event("done")
        return

    
    # 섹션 범위 계산 (ToC 기반으로 정확한 섹션 끝 찾기)
    section_start, section_end = _find_section_page_range(toc, coarse_pages, total_pages)
    section_size = section_end - section_start + 1
    
    # ─── Step 2: 텍스트 기반 정밀 탐색 (Phase 2) ───
    if section_size > 3:
        yield _sse_event("reasoning", content=f"[세부 탐색] '{coarse_title}' 섹션(p.{section_start}~{section_end})의 텍스트를 분석하여 정확한 페이지를 찾고 있습니다...")
        
        phase2_result = _refine_pages_with_text(doc, section_start, section_end, question)
        target_pages = phase2_result.get("target_pages", coarse_pages)
        refined_title = phase2_result.get("section_title", coarse_title)
        refined_reasoning = phase2_result.get("reasoning", "")
        
        yield _sse_event(
            "reasoning",
            content=f"[세부 탐색] '{refined_title}' → 타겟 페이지 {target_pages}\n{refined_reasoning}"
        )
    else:
        # 섹션이 작으면 Phase 1 결과를 그대로 사용
        target_pages = coarse_pages
    
    # ─── Step 4: 미니 PDF 추출 + 참조 이미지 생성 ───
    yield _sse_event("reasoning", content=f"페이지 {target_pages}에서 미니 PDF를 추출하고 있습니다...")
    
    try:
        valid_pages = [_normalize_page(p) - 1 for p in target_pages if 1 <= _normalize_page(p) <= total_pages]
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
        logger.error(f"❌ [Pipeline] PDF 처리 및 참조 이미지 생성 실패: {e}", exc_info=True)
        yield _sse_event("error", content=f"PDF 처리 중 오류: {str(e)}")
        yield _sse_event("done")
        return

    
    # ─── Step 5: Vision LLM 분석 (스트리밍) ───
    yield _sse_event("reasoning", content="Gemini Vision으로 페이지를 분석하고 있습니다...")
    
    try:
        async for chunk in analyze_pages_with_vision(mini_pdf_bytes, question, chat_history=chat_history):
            yield _sse_event("answer", content=chunk)
    except Exception as e:
        logger.error(f"❌ [Pipeline] Vision 분석 중 오류 발생: {e}", exc_info=True)
        yield _sse_event("error", content=f"Vision 분석 중 오류: {str(e)}")
    
    logger.info("🏁 [Pipeline] Agentic Search 파이프라인 처리 완료")
    yield _sse_event("done")

