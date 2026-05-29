"""
Gemini AI 기반 에이전트 서비스.

ToC 추출, 타겟 페이지 추론, Vision 분석 등 LLM 호출 로직을 담당합니다.
"""
import json
import base64
from typing import List, Dict, Any, AsyncGenerator
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from app.config import settings


def _create_llm(temperature: float = 0, model: str | None = None) -> ChatGoogleGenerativeAI:
    """Gemini LLM 인스턴스를 생성합니다. model을 지정하면 해당 모델을 사용합니다."""
    return ChatGoogleGenerativeAI(
        model=model or settings.GEMINI_MODEL_NAME,
        temperature=temperature,
        api_key=settings.GEMINI_API_KEY,
    )


def _create_flash_llm(temperature: float = 0) -> ChatGoogleGenerativeAI:
    """추론/분석용 경량 Flash 모델을 생성합니다. Pro보다 빠르고 저렴합니다."""
    return _create_llm(temperature=temperature, model=settings.GEMINI_FLASH_MODEL_NAME)


def _extract_text_content(content) -> str:
    """
    LLM 응답의 content를 문자열로 변환합니다.
    
    일부 모델(3.1 등)은 content를 리스트(multipart)로 반환할 수 있습니다.
    예: [{"type": "text", "text": "..."}] 또는 ["text1", "text2"]
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _clean_json_response(content) -> str:
    """LLM 응답에서 마크다운 코드 블록을 제거합니다."""
    content = _extract_text_content(content).strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def extract_toc_with_gemini(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    미니 PDF(또는 짧은 전체 PDF)를 Gemini에 전송하여 목차(ToC)를 JSON 형태로 추출합니다.
    """
    llm = _create_flash_llm()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    prompt = """
    You are an expert technical manual analyst.
    Please extract the Table of Contents (ToC) from the provided PDF document.
    Return ONLY a raw JSON array without any markdown formatting like ```json.
    
    The JSON array must contain objects with the following structure:
    [
      {
        "level": 1, 
        "title": "Chapter Name", 
        "page": 5
      }
    ]
    
    - 'level': integer (1 for main chapters, 2 for sub-chapters, etc.)
    - 'title': string (the title of the section)
    - 'page': integer (the physical page number where it starts, typically 1-indexed based on the document)
    
    Extract as much structural hierarchy as possible.
    """
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:application/pdf;base64,{pdf_base64}"
                }
            }
        ]
    )
    
    try:
        response = llm.invoke([message])
        content = _clean_json_response(response.content)
        toc = json.loads(content)
        return toc
    except Exception as e:
        print(f"Gemini ToC Extraction Error: {e}")
        return []


def find_and_extract_toc(
    doc,  # fitz.Document
    total_pages: int,
) -> List[Dict[str, Any]]:
    """
    PDF에서 목차 페이지를 찾아 세부 ToC를 추출합니다.
    
    업로드 시 1회 실행, 결과는 metadata.json에 저장됩니다.
    
    Step 1: 앞부분(~10p) 스캔 → "목차 페이지가 어디 있나?" 파악 (Vision 1회)
    Step 2: 목차 페이지를 읽어 세부 항목 추출 (Vision 1~2회)
    """
    from app.services.pdf_service import extract_pages_as_pdf

    llm = _create_flash_llm()
    
    # ─── Step 1: 목차 페이지 위치 파악 ───
    scan_end = min(24, total_pages - 1)  # 0-indexed, 최대 25페이지
    mini_pdf = extract_pages_as_pdf(doc, 0, scan_end)
    pdf_base64 = base64.b64encode(mini_pdf).decode("utf-8")
    
    find_prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
첨부된 PDF는 전체 {total_pages}페이지 매뉴얼의 앞부분(1~{scan_end + 1}페이지)입니다.

이 페이지들을 분석하여 **목차(Table of Contents) 페이지**가 어디에 있는지 찾아주세요.

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "has_toc": true 또는 false,
    "toc_pages": [목차가_있는_절대_페이지_번호들],
    "toc_extends_beyond": true 또는 false,
    "estimated_toc_end_page": 목차가_끝나는_추정_절대_페이지_번호,
    "note": "분석 결과 요약"
}}

규칙:
- "has_toc": 목차 페이지가 발견되었으면 true
- "toc_pages": 스캔 범위 내에서 목차가 있는 페이지 번호 (1-indexed 절대 번호)
- "toc_extends_beyond": 목차가 스캔 범위({scan_end + 1}페이지)를 넘어서 계속될 것 같으면 true
- "estimated_toc_end_page": 목차가 대략 몇 페이지까지 이어질지 추정 (스캔 범위 안이면 마지막 목차 페이지)
- 목차 외의 페이지(표지, 안전 주의사항, 서문 등)는 제외하세요
"""
    
    message = HumanMessage(content=[
        {"type": "text", "text": find_prompt},
        {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
    ])
    
    try:
        response = llm.invoke([message])
        find_result = json.loads(_clean_json_response(response.content))
    except Exception as e:
        print(f"  ⚠️ 목차 위치 파악 실패: {e}")
        return []
    
    if not find_result.get("has_toc", False):
        print("  ❌ 목차 페이지를 찾을 수 없습니다.")
        return []
    
    toc_pages_found = find_result.get("toc_pages", [])
    extends_beyond = find_result.get("toc_extends_beyond", False)
    estimated_end = find_result.get("estimated_toc_end_page", scan_end + 1)
    
    print(f"  📍 목차 페이지 발견: {toc_pages_found} (스캔 범위 초과: {extends_beyond})")
    
    # ─── Step 2: 목차 페이지 범위 확정 및 읽기 ───
    # 실제 읽을 목차 범위 결정
    if extends_beyond and estimated_end > scan_end + 1:
        # 목차가 스캔 범위를 넘어서면, 추정 끝 페이지까지 확장
        read_start = min(toc_pages_found) - 1 if toc_pages_found else 0  # 0-indexed
        read_end = min(estimated_end - 1, total_pages - 1)  # 0-indexed
    elif toc_pages_found:
        read_start = min(toc_pages_found) - 1  # 0-indexed
        read_end = max(toc_pages_found) - 1  # 0-indexed
    else:
        return []
    
    # 목차 페이지가 너무 많으면 제한 (최대 15페이지)
    if read_end - read_start > 14:
        read_end = read_start + 14
    
    print(f"  📖 목차 읽기 범위: p.{read_start + 1}~{read_end + 1}")
    
    toc_pdf = extract_pages_as_pdf(doc, read_start, read_end)
    toc_base64 = base64.b64encode(toc_pdf).decode("utf-8")
    
    extract_prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
첨부된 PDF는 전체 {total_pages}페이지 매뉴얼의 **목차 페이지**입니다.
이 목차의 모든 항목을 빠짐없이 추출하세요.

다음 JSON 배열로만 응답하세요 (마크다운 코드블록 없이):
[
  {{"level": 1, "title": "장/챕터 제목", "page": 절대_페이지_번호}},
  {{"level": 2, "title": "절/소제목", "page": 절대_페이지_번호}},
  {{"level": 3, "title": "소절", "page": 절대_페이지_번호}}
]

⚠️ 중요 규칙:
- page는 반드시 **절대 페이지 번호(정수)**를 사용하세요.
- 매뉴얼 내부 표기(예: "3-32", "5-1")가 있으면 다음과 같이 변환하세요:
  * 해당 챕터의 시작 절대 페이지를 기준으로 계산
  * 예: 3장이 절대 66페이지에서 시작하고 내부 "3-32"이면 → 66 + 32 - 1 = 97
- 만약 내부 페이지 번호를 절대 번호로 변환할 수 없으면, 내부 번호를 그대로 문자열로 적어주세요.
- level 1=장(Chapter), level 2=절(Section), level 3=소절(Subsection)
- 최대한 많은 항목을 추출하세요.
"""
    
    message = HumanMessage(content=[
        {"type": "text", "text": extract_prompt},
        {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{toc_base64}"}}
    ])
    
    try:
        response = llm.invoke([message])
        raw_toc = json.loads(_clean_json_response(response.content))
    except Exception as e:
        print(f"  ⚠️ 목차 추출 실패: {e}")
        return []
    
    # ─── 페이지 번호 정규화 ───
    import re
    normalized: List[Dict[str, Any]] = []
    
    for item in raw_toc:
        page = item.get("page")
        title = item.get("title", "")
        level = item.get("level", 1)
        
        if isinstance(page, int) and 1 <= page <= total_pages:
            normalized.append({"level": level, "title": title, "page": page})
        elif isinstance(page, str):
            # "3-32" 같은 내부 표기 → 일단 추가 (추후 정규화 가능)
            match = re.match(r"(\d+)-(\d+)", page)
            if match:
                # 내부 표기를 그대로 저장 (정확한 변환은 섹션 정보 필요)
                normalized.append({"level": level, "title": title, "page": page})
            elif page.isdigit():
                p = int(page)
                if 1 <= p <= total_pages:
                    normalized.append({"level": level, "title": title, "page": p})
    
    print(f"  📋 ToC 추출 완료: {len(normalized)}개 항목")
    return normalized


def reason_target_pages(toc: List[Dict[str, Any]], question: str) -> Dict[str, Any]:
    """
    ToC(목차)와 사용자 질문을 기반으로, 가장 관련성 높은 타겟 페이지를 추론합니다.
    
    Returns:
        {
            "reasoning": "추론 과정 텍스트",
            "target_pages": [45, 46, 47],
            "section_title": "관련 섹션 제목"
        }
    """
    llm = _create_flash_llm()
    
    toc_text = json.dumps(toc, ensure_ascii=False, indent=2)
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 PDF 매뉴얼의 목차(Table of Contents)입니다:

{toc_text}

사용자의 질문: "{question}"

위 목차를 분석하여, 이 질문에 답하기 위해 참조해야 할 가장 관련성 높은 페이지 범위를 추론하세요.

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "reasoning": "추론 과정을 한국어로 상세히 설명",
    "target_pages": [시작페이지, ..., 끝페이지],
    "section_title": "관련 섹션의 제목"
}}

규칙:
- 타겟 페이지는 최소 1개, 최대 5개로 제한합니다.
- 페이지 번호는 목차에 명시된 page 값을 기준으로 합니다.
- 연속된 페이지라면 사이 페이지도 포함합니다 (예: 45페이지 섹션이면 45,46,47).
"""
    
    message = HumanMessage(content=prompt)
    
    try:
        response = llm.invoke([message])
        content = _clean_json_response(response.content)
        result = json.loads(content)
        
        # 타겟 페이지가 5개를 초과하면 자르기
        if len(result.get("target_pages", [])) > 5:
            result["target_pages"] = result["target_pages"][:5]
        
        return result
    except Exception as e:
        print(f"Page Reasoning Error: {e}")
        return {
            "reasoning": f"페이지 추론 중 오류 발생: {str(e)}",
            "target_pages": [1],
            "section_title": "알 수 없음"
        }


async def analyze_pages_with_vision(
    pdf_bytes: bytes,
    question: str,
    chat_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    미니 PDF를 Gemini Vision에 전송하여 질문에 대한 답변을 스트리밍으로 생성합니다.
    
    Args:
        pdf_bytes: 분석할 미니 PDF
        question: 사용자 질문
        chat_history: 이전 대화 이력 [{"role": "user"|"assistant", "content": "..."}]
    
    Yields:
        답변 텍스트 청크 (마크다운 형식)
    """
    llm = _create_llm(temperature=0.1)
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    # 이전 대화 맥락 구성
    history_text = ""
    if chat_history:
        # 최근 6턴(3쌍)만 포함 — 토큰 절약
        recent = chat_history[-6:]
        pairs = []
        for item in recent:
            role_label = "사용자" if item["role"] == "user" else "AI"
            pairs.append(f"{role_label}: {item['content'][:300]}")
        history_text = "\n".join(pairs)
    
    context_section = ""
    if history_text:
        context_section = f"""
이전 대화 맥락:
---
{history_text}
---
위 대화를 참고하여, 사용자의 후속 질문에 자연스럽게 답변하세요.
"""
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
첨부된 PDF 페이지를 분석하여 아래 질문에 정확하게 답변하세요.
{context_section}
질문: "{question}"

답변 형식 (마크다운):
## 답변 요약
(핵심 답변을 1-2문장으로)

### 상세 내용
(매뉴얼 내용을 기반으로 상세하게)

### 조치 방법 (해당 시)
1. 단계별 조치 방법
2. ...

> 참고: 해당 정보는 매뉴얼의 첨부 페이지에서 확인된 내용입니다.

규칙:
- 시각적 정보(표, 도면, 다이어그램)가 있다면 해당 내용을 텍스트로 설명해 주세요.
- 매뉴얼에 없는 내용은 추측하지 마세요.
- 한국어로 답변하세요.
"""
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:application/pdf;base64,{pdf_base64}"
                }
            }
        ]
    )
    
    async for chunk in llm.astream([message]):
        if chunk.content:
            yield _extract_text_content(chunk.content)


async def extract_document_metadata_with_gemini(pdf_bytes: bytes) -> dict | None:
    """
    첫 페이지 PDF 바이트를 Gemini Vision에 전달하여 문서의 공식 제목, 제조사, 모델 시리즈, 문서 유형을 구조화 추출합니다.
    
    Returns:
        dict: {
            "title": str or None,
            "manufacturer": str or None,
            "model_series": str or None,
            "doc_type": str or None
        }
    """
    llm = _create_flash_llm()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    prompt = """당신은 산업용 매뉴얼 분석 전문가입니다.
첨부된 PDF 페이지(문서의 첫 페이지/표지)를 분석하여 다음 필드를 추출하고 반드시 정확한 JSON 형식으로만 응답해 주세요.

필드 설명:
1. "title": 표지에서 가장 크고 중심이 되는 텍스트를 찾아 제조사(브랜드), 모델명(시리즈), 문서 유형(매뉴얼, 사용 설명서 등)을 조합하여 하나의 대표 제목으로 만드세요.
   - 예: "로보스타 N1 시리즈 알람코드 설명서"
   - 예: "페스토 사용 설명서"
   - 표지 하단이나 구석에 작게 적힌 주소, 연락처, 웹사이트 URL, 문서 번호, 날짜, 개정번호(Rev) 및 저작권 문구는 제목에 포함하지 마세요.
   - 표지에 있는 선택지나 체크박스 목록(예: "취급 및 유지보수 설명서", "GAIN 설정", "알람코드 설명서") 중 특정 항목에 체크 표시(V 등)가 되어 있다면, 전체 제목 혹은 해당 체크된 항목을 적극적으로 반영하여 정확한 제목을 만드세요. 다른 체크되지 않은 항목(예: "GAIN 설정")을 단순 텍스트로 인식해 제목으로 오해하면 안 됩니다.
2. "manufacturer": 문서의 제조사를 나타내는 대표 이름 (예: "미쯔비시", "페스토", "로보스타", "야스카와" 등)을 한국어로 추출하세요. 찾을 수 없는 경우 null을 지정합니다.
3. "model_series": 모델명 또는 시리즈명을 나타내는 이름 (예: "MR-J5", "N1", "MELSEC-Q" 등)을 영어 또는 한글로 추출하세요. 찾을 수 없는 경우 null을 지정합니다.
4. "doc_type": 문서의 유형을 나타내는 이름 (예: "알람코드 설명서", "사용 설명서", "유지보수 매뉴얼", "카탈로그" 등)을 한국어로 추출하세요. 찾을 수 없는 경우 null을 지정합니다.

응답 예시 (반드시 JSON만 반환하세요, 설명이나 백틱 ```json 마크다운은 금지합니다):
{
  "title": "로보스타 N1 시리즈 알람코드 설명서",
  "manufacturer": "로보스타",
  "model_series": "N1",
  "doc_type": "알람코드 설명서"
}
"""
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:application/pdf;base64,{pdf_base64}"
                }
            }
        ]
    )
    
    try:
        response = await llm.ainvoke([message])
        content = _clean_json_response(response.content)
        result = json.loads(content)
        
        # 기본 필드 검증 및 정리
        for key in ["title", "manufacturer", "model_series", "doc_type"]:
            if key not in result:
                result[key] = None
            elif isinstance(result[key], str):
                result[key] = result[key].replace('"', '').replace("'", "").replace("`", "").strip()
                if not result[key] or "error" in result[key].lower() or result[key].lower() == "null":
                    result[key] = None
        
        return result
    except Exception as e:
        print(f"Gemini Metadata Extraction Error: {e}")
        return None


async def extract_document_title_with_gemini(pdf_bytes: bytes) -> str | None:
    """
    첫 페이지 PDF 바이트를 Gemini Vision에 전달하여 문서의 공식 제목을 분석/추출합니다. (비동기, 하위 호환)
    """
    metadata = await extract_document_metadata_with_gemini(pdf_bytes)
    if metadata and metadata.get("title"):
        return metadata["title"]
    return None


def normalize_manufacturer_with_llm(name: str) -> str:
    """
    Gemini LLM을 이용하여, 비표준/한글 제조사명을 동적으로 영어 대문자 표준형으로 변환합니다.
    글로벌 제조사가 아니거나 일반 국내 업체인 경우 한글 이름을 그대로 보존합니다.
    """
    if not name:
        return name
        
    llm = _create_flash_llm()
    prompt = f"""
    당신은 글로벌 산업용 하드웨어 및 자동화 장비 제조사 브랜드 전문가입니다.
    제시된 제조사명 '{name}'이 세계적으로 널리 알려진 외산/글로벌 브랜드이거나 대기업(예: Keyence, Omron, Mitsubishi, Festo, Siemens, Yaskawa, LG 등)인 경우, 
    공식 표준 영문 대문자(예: KEYENCE, OMRON, MITSUBISHI, FESTO, SIEMENS, YASKAWA, LG 등)로 변환해 주세요.
    
    만약 국내 특수 솔루션 업체나 널리 알려지지 않은 일반 중소기업(예: 네오정보시스템, 라디언큐바이오 등)이라면,
    영어로 억지로 바꾸지 말고 원래 제공된 한글 이름 그대로 반환하십시오.
    
    오직 변환된 단어 하나만 반환하십시오. 마크다운 기호나 추가적인 설명은 절대 금지합니다.
    """
    
    message = HumanMessage(content=prompt)
    try:
        response = llm.invoke([message])
        content = _extract_text_content(response.content).strip()
        # 공백이나 따옴표 제거
        cleaned = content.replace('"', '').replace("'", "").replace("`", "").strip()
        # 간혹 마크다운이 들어가면 제거
        if " " in cleaned and "\n" in cleaned:
            cleaned = cleaned.split("\n")[0].strip()
        return cleaned
    except Exception as e:
        print(f"Gemini Manufacturer Normalization Error: {e}")
        return name.strip().upper()
