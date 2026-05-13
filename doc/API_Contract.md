# 📡 API Contract: Vision RAG

> Backend(FastAPI) ↔ Frontend(Next.js) 간 통신 규약
> 
> 작성일: 2026-05-12 | 버전: v1.0

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

PDF 파일을 업로드하고 목차(ToC)를 추출합니다.

#### 요청

| 항목 | 값 |
|------|-----|
| **Content-Type** | `multipart/form-data` |
| **파일 크기 제한** | 없음 |

```
FormData {
  file: File (application/pdf)
}
```

#### 응답 — `200 OK`

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "inverter_manual_v3.pdf",
  "total_pages": 280,
  "toc": [
    { "level": 1, "title": "1. 제품 개요", "page": 1 },
    { "level": 2, "title": "1.1 사양", "page": 3 },
    { "level": 2, "title": "1.2 외형도", "page": 5 },
    { "level": 1, "title": "2. 설치 방법", "page": 10 },
    { "level": 1, "title": "3. 알람 코드", "page": 45 }
  ],
  "status": "indexed"
}
```

> **스캔 PDF (50페이지 초과)** 인 경우, 목차를 자동 추출할 수 없으므로 다른 응답을 반환합니다:

```json
{
  "document_id": "550e8400-...",
  "filename": "old_scanned_manual.pdf",
  "total_pages": 320,
  "toc": [],
  "status": "toc_required"
}
```

> 프론트엔드는 `status: "toc_required"` 수신 시 사용자에게 목차 페이지 범위 입력 다이얼로그를 표시하고, `POST /upload/toc`를 호출합니다.

#### 에러 응답

| Status | 상황 |
|--------|------|
| `400` | PDF가 아닌 파일 업로드 시 |
| `422` | 파일 필드 누락 시 |
| `500` | PDF 파싱 실패 시 |

---

## 1-2. 목차 범위 지정 (스캔 PDF 전용)

### `POST /upload/toc`

`status: "toc_required"`로 반환된 문서에 대해, 사용자가 지정한 목차 페이지 범위를 전송하여 ToC를 재추출합니다.

#### 요청

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_start_page": 1,
  "toc_end_page": 5
}
```

#### 응답 — `200 OK`

```json
{
  "document_id": "550e8400-...",
  "filename": "old_scanned_manual.pdf",
  "total_pages": 320,
  "toc": [
    { "level": 1, "title": "1. 제품 개요", "page": 1 },
    { "level": 1, "title": "2. 설치", "page": 15 }
  ],
  "status": "indexed"
}
```

---

## 2. 문서 목록 조회

### `GET /documents`

업로드된 모든 문서 목록을 반환합니다. (동시 복수 문서 지원)

#### 응답 — `200 OK`

```json
{
  "documents": [
    {
      "document_id": "550e8400-...",
      "filename": "inverter_manual_v3.pdf",
      "total_pages": 280,
      "uploaded_at": "2026-05-12T14:30:00Z"
    },
    {
      "document_id": "660f9500-...",
      "filename": "plc_troubleshooting.pdf",
      "total_pages": 150,
      "uploaded_at": "2026-05-12T15:00:00Z"
    }
  ]
}
```

---

## 3. 문서 삭제

### `DELETE /documents/{document_id}`

#### 응답 — `200 OK`

```json
{
  "status": "deleted",
  "document_id": "550e8400-..."
}
```

#### 에러 응답

| Status | 상황 |
|--------|------|
| `404` | 존재하지 않는 document_id |

---

## 4. 질의·응답 (스트리밍)

### `POST /chat`

사용자 질문을 받아 Agentic Search → Vision LLM 분석 후 **SSE 스트리밍**으로 응답합니다.

#### 요청

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "알람 코드 E-102 해결 방법은?"
}
```

> **참고**: `document_id`로 특정 문서에 대해 질의합니다.

#### 응답 — `200 OK` (SSE Stream)

**Content-Type**: `text/event-stream`

스트리밍은 3단계로 이벤트를 전송합니다:

```
# 1단계: 추론 과정 (reasoning)
data: {"type": "reasoning", "content": "목차 분석 중... '3. 알람 코드' 섹션 발견"}

data: {"type": "reasoning", "content": "p.45-48 범위로 타겟 페이지 특정 완료"}

# 2단계: 참조 페이지 이미지
data: {"type": "reference", "page_number": 45, "image_base64": "data:image/png;base64,..."}

data: {"type": "reference", "page_number": 46, "image_base64": "data:image/png;base64,..."}

# 3단계: 최종 답변 (청크 단위 스트리밍)
data: {"type": "answer", "content": "## 알람 E-102 해결 절차\n"}

data: {"type": "answer", "content": "### 원인\n인버터 과전류 검출\n"}

data: {"type": "answer", "content": "### 조치 방법\n1. 전원을 차단합니다.\n"}

data: {"type": "answer", "content": "2. 모터 배선 상태를 점검합니다.\n"}

# 종료 신호
data: {"type": "done"}
```

#### SSE 이벤트 타입 정리

| type | 설명 | 전송 시점 |
|------|------|-----------|
| `reasoning` | AI 에이전트의 목차 탐색·추론 과정 | 탐색 중 |
| `reference` | 타겟 페이지 썸네일 이미지 (PyMuPDF get_pixmap, Base64 PNG) | 페이지 추출 완료 시 |
| `answer` | 최종 답변 텍스트 (마크다운) 청크 | 답변 생성 중 |
| `error` | 에러 발생 시 | 에러 시점 |
| `done` | 스트리밍 종료 신호 | 완료 시 |

#### 에러 응답

| Status | 상황 |
|--------|------|
| `404` | 존재하지 않는 document_id |
| `422` | question 필드 누락 |
| `500` | LLM 호출 실패 또는 PDF 렌더링 실패 |

---

## 5. Pydantic 스키마 요약 (백엔드 구현 참조)

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

# --- 요청 ---
class ChatRequest(BaseModel):
    document_id: UUID
    question: str

class TocRangeRequest(BaseModel):
    document_id: UUID
    toc_start_page: int
    toc_end_page: int

# --- 응답 ---
class TocItem(BaseModel):
    level: int
    title: str
    page: int

class UploadResponse(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    toc: list[TocItem]
    status: str  # "indexed" | "toc_required"

class DocumentInfo(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    uploaded_at: datetime

class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]

# --- SSE 이벤트 ---
class StreamEvent(BaseModel):
    type: str  # "reasoning" | "reference" | "answer" | "error" | "done"
    content: str | None = None
    page_number: int | None = None
    image_base64: str | None = None
```
