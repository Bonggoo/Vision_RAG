# 📡 API Contract: Vision RAG

> Backend(FastAPI) ↔ Frontend(Next.js) 간 통신 규약
> 
> 작성일: 2026-05-12 | 최종 수정: 2026-05-15 | 버전: v3.0

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

#### ToC 추출 전략

| 케이스 | 조건 | 동작 |
|--------|------|------|
| **A-1** | 북마크 ToC 충분 | 그대로 사용 |
| **A-2** | 북마크 있지만 부실 | Vision으로 목차 페이지 탐색 → 세부 ToC 추출 |
| **B** | 북마크 없음 + 텍스트 PDF | 앞부분 15페이지 Gemini 스캔 |
| **C** | 스캔본 + 50p 초과 | `toc_required` 상태로 반환 → 사용자 범위 지정 필요 |

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
  "total_pages": 942,
  "toc": [
    { "level": 1, "title": "1. 제품 개요", "page": 1 },
    { "level": 2, "title": "1.1 사양", "page": 3 }
  ],
  "status": "indexed"
}
```

> `filename`은 PDF 메타데이터 title → 첫 페이지 제목에서 자동 추출됩니다.
> `status`가 `toc_required`인 경우, `POST /upload/toc`으로 목차 범위를 지정해야 합니다.

---

## 1-1. 스캔 PDF 목차 범위 지정

### `POST /upload/toc`

스캔 PDF(`status: "toc_required"`)에 대해 사용자가 지정한 페이지 범위에서 ToC를 재추출합니다.

#### 요청

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_start_page": 3,
  "toc_end_page": 12
}
```

#### 응답 — `200 OK`

```json
{
  "document_id": "550e8400-...",
  "filename": "문서 제목",
  "total_pages": 942,
  "toc": [
    { "level": 1, "title": "1. 제품 개요", "page": 1 }
  ],
  "status": "indexed"
}
```

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

> `page`는 정수 또는 문자열(예: `"3-32"`)일 수 있습니다. 매뉴얼 내부 페이지 표기를 그대로 보존합니다.

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
  "message": "알람코드 104는 무슨 의미야?",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "chat_history": [
    { "role": "user", "content": "이전 질문" },
    { "role": "assistant", "content": "이전 답변" }
  ]
}
```

> - `document_id`는 **선택사항**입니다. 생략하면 AI가 업로드된 문서 중 가장 적합한 문서를 자동 선택합니다.
> - `chat_history`는 **선택사항**입니다. 멀티턴 대화 시 최근 6턴(3쌍)을 전송하여 맥락을 유지합니다.

#### 응답 — `200 OK` (SSE Stream)

**Content-Type**: `text/event-stream`

```
# Phase 0+1: 문서 선택 + 섹션 추론
data: {"type": "reasoning", "content": "📄 'QD77MS 매뉴얼' → '알람 코드' (p.[45, 48])"}

# Phase 2: 텍스트 기반 정밀 탐색
data: {"type": "reasoning", "content": "[세부 탐색] '알람 코드' 섹션(p.45~60)의 텍스트를 분석..."}

# Phase 2 결과
data: {"type": "reasoning", "content": "[세부 탐색] '알람 코드 목록' → 타겟 페이지 [46, 47]"}

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
| `reasoning` | AI 에이전트의 문서 선택, 목차 탐색, 텍스트 정밀 탐색 과정 |
| `reference` | 타겟 페이지 썸네일 (Base64 PNG, dpi=150) |
| `answer` | 최종 답변 텍스트 (마크다운) 청크 |
| `error` | 에러 발생 시 |
| `done` | 스트리밍 종료 신호 |

---

## Pydantic 스키마 요약

```python
from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional, Union

# --- 요청 ---
class ChatHistoryItem(BaseModel):
    role: str        # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    document_id: Optional[UUID] = None  # None이면 자동 선택
    question: str = Field(..., alias="message")
    chat_history: Optional[List[ChatHistoryItem]] = None
    model_config = {"populate_by_name": True}

class TocRangeRequest(BaseModel):
    document_id: UUID
    toc_start_page: int
    toc_end_page: int

class DocumentUpdateRequest(BaseModel):
    filename: Optional[str] = None

# --- 응답 ---
class TocItem(BaseModel):
    level: int
    title: str
    page: Union[int, str]  # 정수 또는 "3-32" 형식 문자열

class UploadResponse(BaseModel):
    document_id: UUID
    filename: str
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
