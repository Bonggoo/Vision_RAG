# 📡 API Contract: Vision RAG

> Backend(FastAPI) ↔ Frontend(Next.js) 간 통신 규약
> 
> 작성일: 2026-05-12 | 최종 수정: 2026-05-14 | 버전: v2.0

---

## 공통 사항

| 항목 | 값 |
|------|-----|
| **Base URL (개발)** | `http://localhost:8000` |
| **Base URL (운영)** | 배포 후 확정 |
| **인증** | MVP에서는 미적용 (추후 API Key 방식 검토) |
| **Content-Type** | `application/json` (업로드 제외) |
| **에러 형식** | `{ "detail": "에러 메시지" }` + HTTP Status Code |

---

## 1. 문서 업로드

### `POST /upload`

PDF 파일을 업로드하고 목차(ToC)를 추출합니다. 파일명은 PDF 메타데이터/첫 페이지에서 자동 추출됩니다.

#### 요청

| 항목 | 값 |
|------|-----|
| **Content-Type** | `multipart/form-data` |

```
FormData {
  file: File (application/pdf)
}
```

#### 응답 — `200 OK`

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "MELSEC-Q QD77MS형 심플모션 유닛 사용자 매뉴얼",
  "original_filename": "QD77MS_위치결정_매뉴얼.pdf",
  "total_pages": 942,
  "toc": [
    { "level": 1, "title": "1. 제품 개요", "page": 1 },
    { "level": 2, "title": "1.1 사양", "page": 3 }
  ],
  "status": "indexed"
}
```

> `filename`은 PDF 메타데이터 title → 첫 페이지 제목에서 자동 추출됩니다.
> `original_filename`에 원본 업로드 파일명이 보존됩니다.

---

## 2. 문서 목록 조회

### `GET /documents`

```json
{
  "documents": [
    {
      "document_id": "550e8400-...",
      "filename": "QD77MS 위치결정 매뉴얼",
      "total_pages": 942,
      "uploaded_at": "2026-05-12T14:30:00"
    }
  ]
}
```

---

## 3. 문서 상세 정보

### `GET /documents/{document_id}`

```json
{
  "document_id": "550e8400-...",
  "filename": "QD77MS 위치결정 매뉴얼",
  "total_pages": 942,
  "status": "indexed",
  "uploaded_at": "2026-05-12T14:30:00",
  "toc_count": 291
}
```

---

## 4. 문서 메타데이터 수정 (파일명 등)

### `PATCH /documents/{document_id}`

#### 요청

```json
{
  "filename": "새로운 문서 이름"
}
```

#### 응답 — `200 OK`

```json
{
  "status": "updated",
  "document_id": "550e8400-...",
  "filename": "새로운 문서 이름"
}
```

---

## 5. 문서 삭제

### `DELETE /documents/{document_id}`

```json
{
  "status": "deleted",
  "document_id": "550e8400-..."
}
```

---

## 6. ToC 조회

### `GET /documents/{document_id}/toc`

```json
{
  "document_id": "550e8400-...",
  "toc": [
    { "level": 1, "title": "1 안전상의 주의", "page": 1 },
    { "level": 2, "title": "1.1 사양", "page": 3 }
  ],
  "toc_count": 291
}
```

---

## 7. ToC 재추출 (Vision 기반)

### `POST /documents/{document_id}/reindex`

기존 문서의 ToC를 Vision 기반으로 재보강합니다.

```json
{
  "status": "reindexed",
  "document_id": "550e8400-...",
  "toc_count_before": 8,
  "toc_count_after": 291
}
```

---

## 8. 질의·응답 (SSE 스트리밍)

### `POST /chat/stream`

#### 요청

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "알람코드 104는 무슨 의미야?",
  "chat_history": [
    { "role": "user", "content": "이전 질문" },
    { "role": "assistant", "content": "이전 답변" }
  ]
}
```

> `chat_history`는 선택사항입니다. 멀티턴 대화 시 최근 6턴(3쌍)을 전송하여 맥락을 유지합니다.

#### 응답 — `200 OK` (SSE Stream)

**Content-Type**: `text/event-stream`

```
# Phase 1: 추론 과정
data: {"type": "reasoning", "content": "[Phase 1] '알람 코드' 섹션 특정 완료 (p.45~48)"}

# Phase 2: 세부 페이지 탐색
data: {"type": "reasoning", "content": "[Phase 2] Vision 스캔으로 타겟 페이지 [46, 47] 특정"}

# 참조 이미지
data: {"type": "reference", "page_number": 46, "image_base64": "data:image/png;base64,..."}

# 답변 (청크 단위)
data: {"type": "answer", "content": "## 답변 요약\n"}
data: {"type": "answer", "content": "알람코드 104는 하드웨어 스트로크 리미트+..."}

# 종료
data: {"type": "done"}
```

#### SSE 이벤트 타입

| type | 설명 |
|------|------|
| `reasoning` | AI 에이전트의 목차 탐색·추론 과정 |
| `reference` | 타겟 페이지 썸네일 (Base64 PNG) |
| `answer` | 최종 답변 텍스트 (마크다운) 청크 |
| `error` | 에러 발생 시 |
| `done` | 스트리밍 종료 신호 |

---

## Pydantic 스키마 요약

```python
from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional

# --- 요청 ---
class ChatHistoryItem(BaseModel):
    role: str        # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    document_id: UUID
    question: str = Field(..., alias="message")
    chat_history: Optional[List[ChatHistoryItem]] = None

class DocumentUpdateRequest(BaseModel):
    filename: Optional[str] = None

# --- 응답 ---
class TocItem(BaseModel):
    level: int
    title: str
    page: int

class UploadResponse(BaseModel):
    document_id: UUID
    filename: str
    original_filename: str
    total_pages: int
    toc: list[TocItem]
    status: str  # "indexed" | "toc_required"

# --- SSE 이벤트 ---
class StreamEvent(BaseModel):
    type: str  # "reasoning" | "reference" | "answer" | "error" | "done"
    content: str | None = None
    page_number: int | None = None
    image_base64: str | None = None
```
