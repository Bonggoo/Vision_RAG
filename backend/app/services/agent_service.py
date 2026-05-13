import json
import base64
from typing import List, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from app.config import settings

def extract_toc_with_gemini(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    미니 PDF(또는 짧은 전체 PDF)를 Gemini에 전송하여 목차(ToC)를 JSON 형태로 추출합니다.
    """
    # ==========================================
    # [임시 Mock 로직] API 무한 대기 이슈로 임시 더미 데이터 리턴
    # ==========================================
    print("\n[Mock] Gemini API 호출을 스킵하고 더미 목차를 반환합니다...")
    return [
        {"level": 1, "title": "1. 안전을 위한 주의사항", "page": 4},
        {"level": 2, "title": "1.1 경고 및 주의", "page": 4},
        {"level": 1, "title": "2. 시스템 구성", "page": 12},
        {"level": 2, "title": "2.1 전체 시스템", "page": 12},
        {"level": 2, "title": "2.2 각부 명칭", "page": 15},
        {"level": 1, "title": "3. 배선 및 설치", "page": 20},
    ]
    # ==========================================
    
    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL_NAME,
        temperature=0,
        api_key=settings.GEMINI_API_KEY
    )
    
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
                "type": "image_url", # langchain-google-genai uses image_url for base64 files
                "image_url": {
                    "url": f"data:application/pdf;base64,{pdf_base64}"
                }
            }
        ]
    )
    
    try:
        response = llm.invoke([message])
        content = response.content.strip()
        
        # ```json 등 마크다운 제거
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
            
        toc = json.loads(content.strip())
        return toc
    except Exception as e:
        print(f"Gemini ToC Extraction Error: {e}")
        return []
