# 📡 API Contract: Vision RAG

> Backend(FastAPI) ↔ Frontend(Next.js) 간 통신 규약
> 
> 작성일: 2026-05-12 | 최종 수정: 2026-06-09 | 버전: v4.0

---

## 공통 사항

| 항목 | 값 |
|------|-----|
| **Base URL (개발)** | `http://localhost:8000` |
| **Base URL (운영)** | 배포 후 확정 (Cloud Run URL) |
| **인증** | 구글 OAuth 2.0 기반 자체 JWT 인증 (`Authorization: Bearer <JWT>`) |
| **인증 예외** | `/api/auth/google`, `/api/auth/refresh` (이외 모든 엔드포인트는 인증 필수) |
| **Content-Type** | `application/json` (동기식 `/upload` 멀티파트 업로드 제외) |
| **에러 형식** | `{ "detail": "에러 메시지" }` + HTTP Status Code |

---

## 0. 인증 (Authentication)

### 0-1. 구글 로그인 및 JWT 발급
### `POST /api/auth/google`

구글 OAuth 로그인 후 백엔드 서비스 전용 Access / Refresh Token 쌍을 발급받습니다.

#### 요청
```json
{
  "credential": "eyJhbGciOiJSUzI1NiIs..." // Google이 발행한 ID Token JWT
}
```

#### 응답 — `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "refresh_token": "eyJhbGciOiJIUzI1Ni...",
  "token_type": "bearer",
  "email": "user@example.com",
  "name": "홍길동",
  "picture": "https://lh3.googleusercontent.com/..."
}
```

---

### 0-2. 토큰 재발급
### `POST /api/auth/refresh`

만료된 Access Token을 갱신하기 위해 Refresh Token을 사용하여 새로운 토큰 세트를 발급받습니다.

#### 요청
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1Ni..."
}
```

#### 응답 — `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "refresh_token": "eyJhbGciOiJIUzI1Ni...",
  "token_type": "bearer"
}
```

---

## 1. 문서 업로드 (하이브리드 지원)

### 1-1. [동기식] 파일 업로드 (20MB 미만 소형 파일 권장)
### `POST /upload`

PDF 파일을 직접 업로드하고 동기적으로 목차(ToC)를 분석 및 추출합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`
* **Content-Type**: `multipart/form-data`

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
    { "level": 1, "title": "1. 제품 개요", "page": 1 }
  ],
  "status": "indexed",
  "manufacturer": "MITSUBISHI",
  "model_series": "MELSEC-Q",
  "doc_type": "사용자 매뉴얼",
  "uploaded_at": "2026-06-09T14:30:00Z"
}
```

---

### 1-2. [비동기식] 업로드 사전 검증
### `POST /upload/preflight`

대용량 파일 업로드 전 중복 체크를 수행하고, GCS에 다이렉트 업로드할 수 있는 임시 서명 URL(Signed URL)을 발급받습니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

```json
{
  "file_hash": "230ade91bc...", // 브라우저에서 계산한 파일의 SHA-256 해시값
  "file_size": 34520912,        // 파일 용량 (Bytes)
  "filename": "qd77ms_manual.pdf"
}
```

#### 응답 — `200 OK`
```json
{
  "status": "approved",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_url": "https://storage.googleapis.com/..." // GCS Signed Upload URL (PUT). 로컬 스토리지 모드 시 null 반환하여 동기 Fallback 유도.
}
```

* **참고**: GCS Signed URL 수신 후 프론트엔드는 해당 URL에 `PUT` 메서드로 바이너리를 직접 전송(0.1초 반응 및 백엔드 메모리 보호)한 뒤, `/upload/analyze`를 호출합니다.

---

### 1-3. [비동기식] 비동기 분석 트리거
### `POST /upload/analyze`

GCS 업로드 완료 후, 백엔드에 백그라운드 AI 분석(ToC 및 표지 자동 분류) 작업을 지시합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "qd77ms_manual.pdf",
  "file_hash": "230ade91bc..."
}
```

#### 응답 — `200 OK`
```json
{
  "status": "analyzing",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "AI 비동기 분석 작업이 큐에 성공적으로 등록되었습니다."
}
```

---

### 1-4. 스캔 PDF 목차 범위 지정
### `POST /upload/toc`

Status가 `toc_required`인 대용량 스캔 PDF에 대해 사용자가 지정한 범위에서 ToC를 추출합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

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
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
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

현재 로그인한 사용자가 소유한 모든 문서 목록을 반환합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "documents": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "QD77MS 위치결정 매뉴얼",
      "total_pages": 942,
      "uploaded_at": "2026-06-09T14:30:00Z",
      "status": "indexed",
      "manufacturer": "MITSUBISHI",
      "model_series": "MELSEC-Q",
      "doc_type": "사용자 매뉴얼"
    }
  ]
}
```

---

## 3. 문서 상세 정보
### `GET /documents/{document_id}`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "QD77MS 위치결정 매뉴얼",
  "total_pages": 942,
  "status": "indexed",
  "uploaded_at": "2026-06-09T14:30:00Z",
  "toc_count": 291
}
```

---

## 4. 문서 메타데이터 수정 (파일명 등)
### `PATCH /documents/{document_id}`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

```json
{
  "filename": "새로운 문서 이름",
  "manufacturer": "MITSUBISHI",
  "model_series": "MELSEC-Q"
}
```

#### 응답 — `200 OK`
```json
{
  "status": "updated",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "새로운 문서 이름",
  "manufacturer": "MITSUBISHI",
  "model_series": "MELSEC-Q"
}
```

---

## 5. 문서 삭제
### `DELETE /documents/{document_id}`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "status": "deleted",
  "document_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 6. 문서 다운로드

### 6-1. [서버 중개] 직접 파일 다운로드
### `GET /documents/{document_id}/download`

백엔드 로컬 스레드를 거쳐 파일을 다운로드합니다. 한글 파일명 깨짐 방지 명세(RFC 5987)가 적용되어 있습니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
* **Content-Type**: `application/pdf`
* **Response Headers**:
  `Content-Disposition: attachment; filename="document.pdf"; filename*=UTF-8''%EC%A0%9C%EC%A1%B0%EC%82%AC_%EB%AA%A8%EB%8D%B8...pdf`

---

### 6-2. [고속] 다운로드 보안 링크 발급
### `GET /documents/{document_id}/download-url`

대기 없는 초고속 다운로드를 위해 GCS Signed URL을 발급받거나 로컬 다운로드 URL로 분기 처리합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "mode": "gcs", // "gcs" | "local"
  "url": "https://storage.googleapis.com/...", // GCS Signed URL 또는 로컬 경로 (/documents/{id}/download)
  "filename": "MITSUBISHI_MELSEC-Q_사용자매뉴얼.pdf"
}
```

---

## 7. 미분류 문서 일괄 재분류
### `POST /documents/reclassify`

제조사 또는 모델 시리즈가 지정되지 않은 미분류 문서들을 백그라운드에서 순차적으로 Gemini Vision 분석을 통해 자동 매핑합니다.

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `202 Accepted`
```json
{
  "status": "started",
  "message": "미분류 문서 3건의 재분류가 시작되었습니다...",
  "count": 3
}
```

---

## 8. ToC 조회 및 재보강

### 8-1. ToC 전체 조회
### `GET /documents/{document_id}/toc`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc": [
    { "level": 1, "title": "1 안전상의 주의", "page": 1 },
    { "level": 2, "title": "1.1 사양", "page": "3-32" }
  ],
  "toc_count": 291
}
```

---

### 8-2. Vision 기반 ToC 재추출
### `POST /documents/{document_id}/reindex`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "status": "reindexed",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "toc_count_before": 8,
  "toc_count_after": 291
}
```

---

## 9. 질의·응답 (SSE 스트리밍)
### `POST /chat/stream`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

```json
{
  "message": "알람코드 104는 무슨 의미야?",
  "document_id": "550e8400-e29b-41d4-a716-446655440000", // 선택사항 (생략 시 소유 문서 중 자동 탐색)
  "chat_history": [
    { "role": "user", "content": "이전 질문" },
    { "role": "assistant", "content": "이전 답변" }
  ],
  "image": "data:image/png;base64,iVBORw0KGgoAAA...", // 선택사항 (모바일 카메라 등으로 입력된 첨부 이미지)
  "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0", // 선택사항 (대화 GCS 저장용 세션 ID)
  "previous_reference": { // 선택사항 (맥락 유지용 직전 참조 문서 정보)
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "document_name": "QD77MS 위치결정 매뉴얼",
    "manufacturer": "MITSUBISHI",
    "referenced_pages": [45, 46]
  }
}
```

#### 응답 — `200 OK` (SSE Stream)
* **Content-Type**: `text/event-stream`

```
# Phase 1: 문서 선택 결과 (되묻기가 필요할 때만 발생)
data: {"type": "clarification", "content": "여러 매뉴얼에서 관련 내용을 찾았습니다. 어떤 장비의 매뉴얼을 참조할까요?", "candidates": [{"document_id": "550e8400...", "title": "QD77MS 매뉴얼", "manufacturer": "MITSUBISHI", "model_series": "MELSEC-Q", "confidence": 0.65}]}

# Phase 1-2: ToC 기반 타겟 섹션 추론
data: {"type": "reasoning", "content": "📄 'QD77MS 매뉴얼' → '알람 코드' (p.[45, 48])"}

# Phase 1-2: 관련 목차 추천 후보군 카드
data: {"type": "toc_cards", "cards": [{"title": "알람 코드 목록", "page": 45}]}

# Phase 2: 텍스트 기반 정밀 탐색
data: {"type": "reasoning", "content": "[세부 탐색] '알람 코드' 섹션(p.45~60)의 텍스트를 분석..."}
data: {"type": "reasoning", "content": "[세부 탐색] '알람 코드 목록' → 타겟 페이지 [46, 47]"}

# 참조 이미지 (페이지 썸네일) 및 문서 메타 정보
data: {"type": "reference", "page_number": 46, "image_base64": "data:image/png;base64,...", "document_id": "550e8400...", "document_name": "QD77MS 위치결정 매뉴얼"}

# 답변 스트리밍 청크
data: {"type": "answer", "content": "## 답변 요약\n"}
data: {"type": "answer", "content": "알람코드 104는 하드웨어 스트로크 리미트+..."}

# 종료
data: {"type": "done"}
```

---

## 10. 대화 세션 관리 (GCS 연동)

### 10-1. 새 대화 세션 생성
### `POST /conversations`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`
```json
{
  "title": "새로운 대화" // 선택사항 (생략 시 기본값: "새로운 대화")
}
```

#### 응답 — `200 OK`
```json
{
  "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0",
  "title": "새로운 대화",
  "created_at": "2026-06-20T05:54:32Z",
  "updated_at": "2026-06-20T05:54:32Z",
  "messages": []
}
```

---

### 10-2. 대화 목록 조회 (최대 20개, 최신순)
### `GET /conversations`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "conversations": [
    {
      "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0",
      "title": "서보 알람 AL.E6 질문",
      "created_at": "2026-06-20T05:54:32Z",
      "updated_at": "2026-06-20T05:58:10Z",
      "message_count": 2
    }
  ]
}
```

---

### 10-3. 단건 대화 상세 조회 (메시지 포함)
### `GET /conversations/{session_id}`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0",
  "title": "서보 알람 AL.E6 질문",
  "created_at": "2026-06-20T05:54:32Z",
  "updated_at": "2026-06-20T05:58:10Z",
  "messages": [
    {
      "role": "user",
      "content": "AL.E6 에러가 무엇인가요?",
      "image": null,
      "timestamp": "2026-06-20T05:54:32Z"
    },
    {
      "role": "assistant",
      "content": "AL.E6은 서보드라이브 과부하 에러입니다...",
      "reasoning_steps": ["단계 1: 알람 감지", "단계 2: 원인 분석"],
      "reference_pages": [140, 141],
      "reference_document_id": "550e8400-e29b-41d4-a716-446655440000",
      "reference_document_name": "MR-J5 서보앰프 기술 매뉴얼",
      "toc_cards": [{"title": "보호 기능 목록", "page": 139}],
      "timestamp": "2026-06-20T05:55:10Z"
    }
  ]
}
```

---

### 10-4. 대화 삭제
### `DELETE /conversations/{session_id}`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`

#### 응답 — `200 OK`
```json
{
  "status": "deleted",
  "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0"
}
```

---

### 10-5. 대화 제목 변경
### `PATCH /conversations/{session_id}/rename`

#### 요청
* **Headers**: `Authorization: Bearer <JWT>`
```json
{
  "title": "변경할 대화 제목"
}
```

#### 응답 — `200 OK`
```json
{
  "status": "renamed",
  "session_id": "61de98d2-4aa8-4249-8ee8-6179c7e7b1f0",
  "title": "변경할 대화 제목"
}
```

---

## Pydantic 스키마 요약

```python
from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional, Union

# --- 요청 객체 ---
class GoogleLoginRequest(BaseModel):
    credential: str

class RefreshRequest(BaseModel):
    refresh_token: str

class ChatHistoryItem(BaseModel):
    role: str        # "user" | "assistant"
    content: str

class PreviousReference(BaseModel):
    document_id: UUID
    document_name: Optional[str] = None
    manufacturer: Optional[str] = None
    referenced_pages: Optional[List[int]] = None

class ChatRequest(BaseModel):
    document_id: Optional[UUID] = None
    question: str = Field(..., alias="message")
    chat_history: Optional[List[ChatHistoryItem]] = None
    image: Optional[str] = None # Base64 이미지 URL 포맷
    session_id: Optional[str] = None # 대화 GCS 저장용
    previous_reference: Optional[PreviousReference] = None # 맥락 유지용
    
    model_config = {"populate_by_name": True}

class PreflightRequest(BaseModel):
    file_hash: str
    file_size: int
    filename: str

class AnalyzeRequest(BaseModel):
    document_id: UUID
    filename: str
    file_hash: str

class TocRangeRequest(BaseModel):
    document_id: UUID
    toc_start_page: int
    toc_end_page: int

class DocumentUpdateRequest(BaseModel):
    filename: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None

class CreateConversationRequest(BaseModel):
    title: str = "새로운 대화"

class RenameConversationRequest(BaseModel):
    title: str

# --- 응답 객체 ---
class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    email: str
    name: str
    picture: str

class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class PreflightResponse(BaseModel):
    status: str
    document_id: UUID
    upload_url: Optional[str]

class AnalyzeResponse(BaseModel):
    status: str
    document_id: UUID
    message: str

class TocItem(BaseModel):
    level: int
    title: str
    page: Union[int, str]

class UploadResponse(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    toc: List[TocItem]
    status: str
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None
    doc_type: Optional[str] = None
    uploaded_at: str

class StreamEvent(BaseModel):
    type: str # "reasoning" | "reference" | "answer" | "error" | "done" | "clarification" | "toc_cards"
    content: Optional[str] = None
    page_number: Optional[int] = None
    image_base64: Optional[str] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    candidates: Optional[List[dict]] = None
    cards: Optional[List[dict]] = None

class ConversationMessage(BaseModel):
    role: str
    content: str
    image: Optional[str] = None
    reasoning_steps: Optional[List[str]] = None
    reference_pages: Optional[List[int]] = None
    reference_document_id: Optional[str] = None
    reference_document_name: Optional[str] = None
    toc_cards: Optional[List[dict]] = None
    timestamp: Optional[str] = None

class ConversationInfo(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int

class ConversationDetail(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ConversationMessage]

class ConversationListResponse(BaseModel):
    conversations: List[ConversationInfo]
```

