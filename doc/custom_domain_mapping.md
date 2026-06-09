# 🌐 Cloud Run & Vercel 커스텀 도메인 연결 설정 가이드

본 문서는 TechNote(Vision RAG) 시스템의 백엔드(Cloud Run)와 프론트엔드(Vercel)에 커스텀 도메인을 깔끔하게 연결하여, 기본 URL 노출을 차단하고 Same-Site 보안 쿠키 설정을 원활하게 만들기 위한 **인프라 설정 가이드**입니다.

---

## 🏗️ 전체 아키텍처 구성 예시

* **프론트엔드 (Vercel)**: `https://technote.app` (또는 임의의 커스텀 도메인)
* **백엔드 (Cloud Run)**: `https://api.technote.app` (서브도메인 매핑)
> [!TIP]
> 백엔드 도메인을 프론트엔드 도메인의 **서브도메인**으로 매핑하면, 브라우저가 두 도메인을 **Same-Site**로 간주합니다. 이 경우 CORS 및 HttpOnly 쿠키 전달 설정이 가장 유연하고 안전하게 동작합니다.

---

## 🔑 1단계: Google Search Console 도메인 소유권 확인

Cloud Run에 커스텀 도메인을 매핑하려면, 먼저 Google Cloud 프로젝트가 해당 도메인의 소유권을 확인해야 합니다.

1. **Google Search Console**([https://search.google.com/search-console](https://search.google.com/search-console))에 접속합니다.
2. 매핑하고자 하는 도메인(예: `technote.app`)을 추가합니다.
3. 제공되는 **TXT 레코드**를 도메인 등록 기관(가비아, Cloudflare, GoDaddy 등)의 DNS 설정에 추가하여 소유권 인증을 완료합니다.
4. (선택사항) gcloud CLI로도 인증 상태를 체크할 수 있습니다:
   ```bash
   gcloud domains verify technote.app
   ```

---

## 🛠️ 2단계: Cloud Run에 커스텀 도메인 매핑 등록

소유권 확인이 완료되면 Cloud Run 서비스에 도메인을 맵핑합니다.

### 방법 A: Google Cloud Console UI 사용 (권장)
1. **Google Cloud Console** ➔ **Cloud Run** 페이지로 이동합니다.
2. 상단의 **'관리형 도메인 관리 (Manage Custom Domains)'** 버튼을 클릭합니다.
3. **'매핑 추가 (Add Mapping)'**를 클릭합니다.
4. 매핑할 Cloud Run 서비스(`vision-rag-backend`)를 선택합니다.
5. 연결할 도메인 주소(예: `api.technote.app`)를 입력하고 **'완료'**를 누릅니다.

### 방법 B: gcloud CLI 사용
터미널에서 아래 명령을 실행하여 매핑을 생성합니다:
```bash
gcloud beta run domain-mappings create \
  --service=vision-rag-backend \
  --domain=api.technote.app \
  --region=asia-northeast3
```
*(실제 배포된 서비스명과 리전 값으로 치환하여 실행합니다.)*

---

## 📑 3단계: DNS 레코드 업데이트 (도메인 구입처 설정)

매핑을 추가하면, Google Cloud Console 화면에 등록해야 할 **DNS 레코드 정보**가 표시됩니다.

1. 도메인 구입처(예: 가비아, Cloudflare 등)의 **DNS 설정/관리** 페이지로 이동합니다.
2. 아래 예시와 같이 GCP가 제공한 레코드들을 추가합니다.

#### 등록해야 할 DNS 레코드 예시:
* **CNAME 레코드의 경우**:
  | 타입 | 호스트 (Host) | 값 (Value / Target) | TTL |
  | :---: | :--- | :--- | :---: |
  | **CNAME** | `api` | `ghs.googlehosted.com.` | 3600 |

* **A / AAAA 레코드의 경우 (Google이 다중 IP를 주는 경우)**:
  | 타입 | 호스트 (Host) | IP 주소 (Value) |
  | :---: | :--- | :--- |
  | **A** | `api` | `216.239.32.21` (GCP 화면에 표시된 값) |
  | **A** | `api` | `216.239.34.21` |
  | **AAAA** | `api` | `2001:4860:4802:32::15` |

> [!IMPORTANT]
> 레코드 등록 후 DNS 변경 사항이 전 세계에 전파되기까지 **최소 수 분에서 최대 24시간**이 소요될 수 있습니다. 
> 구글은 매핑이 완료되면 자동으로 관리형 **SSL(HTTPS) 인증서**를 생성 및 적용해 줍니다.

---

## 🌐 4단계: 시스템 환경변수(Env) 동기화

도메인 연결이 완료되면, 보안 통신을 위해 백엔드와 프론트엔드의 환경변수를 최신화해야 합니다.

### 1) 백엔드 (Cloud Run 환경변수 수정)
* **`ALLOWED_ORIGINS`**:
  * 프론트엔드의 커스텀 도메인 주소를 허용 목록에 추가합니다.
  * 예: `http://localhost:3000,https://technote.app`

### 2) 프론트엔드 (Vercel 환경변수 수정)
* **`NEXT_PUBLIC_API_URL`**:
  * 기존의 구글 주소(`https://...run.app`)를 새로 만든 백엔드 도메인 주소로 교체합니다.
  * 예: `https://api.technote.app`
* 환경변수 저장 후 Vercel 대시보드에서 **Redeploy(재배포)**를 수행하여 설정을 적용합니다.
