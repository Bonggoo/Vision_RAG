import jwt
import httpx
from datetime import datetime, timezone, timedelta

# 설정
BACKEND_URL = "https://vision-rag-backend-sfsbvktuia-du.a.run.app"
JWT_SECRET = "vision-rag-production-secure-secret-key-9b1cb9e-ff1540"
JWT_ALGORITHM = "HS256"
TEST_EMAIL = "choibong975@gmail.com"
DOC_ID = "bb1a7876-65ea-4230-adac-3926f59a0d36"

def create_test_token(email: str) -> str:
    payload = {
        "email": email,
        "name": "Test User",
        "picture": "",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def check_document_detail():
    token = create_test_token(TEST_EMAIL)
    url = f"{BACKEND_URL}/documents/{DOC_ID}/toc"  # ToC 가져오는 별도 엔드포인트가 있을 수 있음
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    with httpx.Client(timeout=30.0) as client:
        # 우선 일반 상세 정보 조회
        response = client.get(f"{BACKEND_URL}/documents/{DOC_ID}", headers=headers)
        print("Detail status:", response.status_code)
        if response.status_code == 200:
            print(response.json())
            
        # ToC 엔드포인트 조회 시도
        # documents.py 의 139라인 주석에 "전체 ToC는 /toc 엔드포인트 사용"이라 되어 있음
        response_toc = client.get(f"{BACKEND_URL}/documents/{DOC_ID}/toc", headers=headers)
        print("\nToC status:", response_toc.status_code)
        if response_toc.status_code == 200:
            toc_data = response_toc.json()
            toc_list = toc_data.get("toc", [])
            print(f"ToC Entries: {len(toc_list)}")
            
            # 일부 ToC 항목 출력
            for i, entry in enumerate(toc_list[:30]):
                print(f"  [{i+1}] {entry.get('title')}")
            
            # 키워드 매칭 분석
            question = "위치결정모듈 2051 알람"
            import re
            question_keywords = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', question.lower()))
            print("\nQuestion Keywords:", question_keywords)
            
            toc_text = " ".join(str(entry.get("title", "")).lower() for entry in toc_list).lower()
            print("toc_text (first 300 chars):", toc_text[:300])
            
            for kw in question_keywords:
                matched = kw in toc_text
                print(f"Keyword '{kw}' in toc_text? -> {matched}")

if __name__ == "__main__":
    check_document_detail()
