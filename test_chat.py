#!/usr/bin/env python3
"""
Cloud Run 백엔드 채팅 API 로컬 테스트 스크립트.

사용법:
  python test_chat.py "서보 2051 알람 설명"
  python test_chat.py "배터리 교체 방법" --url https://your-cloudrun-url.run.app
"""
import argparse
import json
import sys
import jwt
import httpx
from datetime import datetime, timedelta, timezone


# Cloud Run 배포 URL (실제 URL로 교체하세요)
DEFAULT_BACKEND_URL = "https://vision-rag-backend-sfsbvktuia-du.a.run.app"

# backend/app/config.py의 JWT_SECRET과 동일해야 함
JWT_SECRET = "vision-rag-production-secure-secret-key-9b1cb9e-ff1540"
JWT_ALGORITHM = "HS256"

# 테스트용 이메일 (GCS에 문서가 저장된 계정)
TEST_EMAIL = "choibong975@gmail.com"


def create_test_token(email: str) -> str:
    """백엔드가 인식하는 Access Token 생성"""
    payload = {
        "email": email,
        "name": "Test User",
        "picture": "",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def stream_chat(base_url: str, question: str, email: str):
    """SSE 스트리밍으로 채팅 응답 수신"""
    token = create_test_token(email)
    url = f"{base_url.rstrip('/')}/chat/stream"

    print(f"\n🔗 URL: {url}")
    print(f"📧 Email: {email}")
    print(f"❓ 질문: {question}")
    print("─" * 60)

    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            url,
            json={"message": question},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status_code != 200:
                print(f"❌ HTTP {response.status_code}")
                print(response.read().decode())
                return

            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    event_type = data.get("type", "")

                    if event_type == "reasoning":
                        print(f"🧠 {data['content']}")
                    elif event_type == "reference":
                        page = data.get("page_number", "?")
                        doc = data.get("document_name", "")
                        print(f"📄 참조: p.{page} ({doc})")
                    elif event_type == "answer":
                        sys.stdout.write(data.get("content", ""))
                        sys.stdout.flush()
                    elif event_type == "clarification":
                        print(f"\n🤖 {data['content']}")
                        for q in data.get("suggested_questions", []):
                            print(f"   → {q}")
                        for c in data.get("candidates", []):
                            print(f"   📂 {c['manufacturer']} {c['model_series']} ({c['confidence']*100:.0f}%)")
                    elif event_type == "error":
                        print(f"\n⚠️ 오류: {data['content']}")
                    elif event_type == "done":
                        print("\n" + "─" * 60)
                        print("✅ 완료")
                except json.JSONDecodeError:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vision RAG 채팅 테스트")
    parser.add_argument("question", help="테스트할 질문")
    parser.add_argument("--url", default=DEFAULT_BACKEND_URL, help="백엔드 URL")
    parser.add_argument("--email", default=TEST_EMAIL, help="테스트 이메일")
    args = parser.parse_args()

    stream_chat(args.url, args.question, args.email)
