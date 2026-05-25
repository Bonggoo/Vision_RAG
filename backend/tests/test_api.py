import os
import sys
import json
import argparse
import httpx

# 컬러 터미널 출력을 위한 코드
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def parse_args():
    parser = argparse.ArgumentParser(description="Vision RAG API End-to-End Test 스크립트")
    parser.add_argument(
        "--url", 
        default="http://localhost:8000", 
        help="테스트할 API 서버의 Base URL (기본값: http://localhost:8000)"
    )
    parser.add_argument(
        "--file", 
        required=True, 
        help="테스트에 사용할 PDF 매뉴얼 파일 경로"
    )
    parser.add_argument(
        "--question", 
        default="알람코드 104는 무슨 의미야?", 
        help="테스트용 질문 (기본값: '알람코드 104는 무슨 의미야?')"
    )
    parser.add_argument(
        "--no-cleanup", 
        action="store_true", 
        help="테스트 완료 후 업로드된 문서를 삭제하지 않고 유지합니다."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 0. 파일 존재 여부 확인
    if not os.path.exists(args.file):
        print(f"{Colors.FAIL}❌ 에러: 지정된 파일이 존재하지 않습니다: {args.file}{Colors.ENDC}")
        sys.exit(1)
        
    base_url = args.url.rstrip('/')
    file_path = args.file
    filename = os.path.basename(file_path)
    
    print(f"{Colors.BOLD}{Colors.HEADER}=== Vision RAG E2E API 테스트 시작 ==={Colors.ENDC}")
    print(f"🔗 Target Server: {base_url}")
    print(f"📄 Target File: {file_path} ({filename})")
    print(f"❓ Question: {args.question}")
    print(f"🧹 Cleanup: {'비활성화' if args.no_cleanup else '활성화'}")
    print("======================================\n")
    
    document_id = None
    
    # HTTP 클라이언트 세션 설정 (타임아웃 120초로 넉넉하게 설정)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    client = httpx.Client(base_url=base_url, timeout=120.0, limits=limits)
    
    try:
        # 1. POST /upload - PDF 업로드 및 ToC 인덱싱
        print(f"{Colors.OKBLUE}Step 1. PDF 파일 업로드 중... ({filename}){Colors.ENDC}")
        
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/pdf")}
            response = client.post("/upload", files=files)
            
        if response.status_code != 200:
            print(f"{Colors.FAIL}❌ 업로드 실패 (HTTP {response.status_code}): {response.text}{Colors.ENDC}")
            return
            
        upload_data = response.json()
        document_id = upload_data.get("document_id")
        status = upload_data.get("status")
        total_pages = upload_data.get("total_pages")
        toc_count = len(upload_data.get("toc", []))
        
        print(f"{Colors.OKGREEN}✅ 업로드 성공!{Colors.ENDC}")
        print(f"  - Document ID: {document_id}")
        print(f"  - 상태(Status): {status}")
        print(f"  - 전체 페이지 수: {total_pages}")
        print(f"  - 추출된 ToC 항목 수: {toc_count}")
        print()
        
        # 만약 스캔본이라 ToC 범위 지정이 필요하다면 테스트를 위해 자동으로 첫 5페이지를 지정해 진행해본다.
        if status == "toc_required":
            print(f"{Colors.WARNING}⚠️ 이 문서는 스캔본이므로 목차 범위 지정이 필요합니다.{Colors.ENDC}")
            print(f"{Colors.OKBLUE}자동으로 목차 페이지 범위를 1페이지에서 5페이지로 지정하여 재색인합니다...{Colors.ENDC}")
            
            toc_range_payload = {
                "document_id": document_id,
                "toc_start_page": 1,
                "toc_end_page": min(5, total_pages)
            }
            toc_res = client.post("/upload/toc", json=toc_range_payload)
            if toc_res.status_code == 200:
                toc_data = toc_res.json()
                print(f"{Colors.OKGREEN}✅ 목차 재추출 완료 (항목 수: {len(toc_data.get('toc', []))}){Colors.ENDC}\n")
            else:
                print(f"{Colors.FAIL}❌ 목차 재추출 실패: {toc_res.text}{Colors.ENDC}")
                return
        
        # 2. GET /documents - 문서 목록 조회 및 업로드 검증
        print(f"{Colors.OKBLUE}Step 2. 문서 목록 조회 및 검증 중...{Colors.ENDC}")
        docs_res = client.get("/documents")
        if docs_res.status_code != 200:
            print(f"{Colors.FAIL}❌ 목록 조회 실패: {docs_res.text}{Colors.ENDC}")
            return
            
        docs_data = docs_res.json()
        documents = docs_data.get("documents", [])
        is_found = any(d.get("document_id") == document_id for d in documents)
        
        if is_found:
            print(f"{Colors.OKGREEN}✅ 문서 목록에서 새 ID를 정상적으로 확인했습니다.{Colors.ENDC}\n")
        else:
            print(f"{Colors.FAIL}❌ 오류: 새 문서 ID({document_id})가 목록에서 조회되지 않습니다.{Colors.ENDC}\n")
            return
            
        # 3. POST /chat/stream - SSE 스트리밍 테스트
        print(f"{Colors.OKBLUE}Step 3. 질의·응답 SSE 스트리밍 수행 중...{Colors.ENDC}")
        print(f"질문: {Colors.BOLD}'{args.question}'{Colors.ENDC}\n")
        print(f"{Colors.BOLD}[SSE STREAM START]{Colors.ENDC}")
        
        chat_payload = {
            "message": args.question,
            "document_id": document_id
        }
        
        # SSE를 읽기 위해 httpx.stream 사용
        with client.stream("POST", "/chat/stream", json=chat_payload) as stream:
            if stream.status_code != 200:
                print(f"{Colors.FAIL}❌ 스트리밍 연결 실패 (HTTP {stream.status_code}){Colors.ENDC}")
                # 에러 내용을 확인하기 위해 바디를 읽어 출력
                stream.read()
                print(stream.text)
                return
                
            current_event_type = None
            for line in stream.iter_lines():
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith("data:"):
                    try:
                        # "data: " 접두사 제거 후 JSON 파싱
                        data_json = json.loads(line[5:].strip())
                        event_type = data_json.get("type")
                        
                        if event_type == "reasoning":
                            content = data_json.get("content", "")
                            print(f"{Colors.OKCYAN}[생각 과정] {content}{Colors.ENDC}")
                            
                        elif event_type == "reference":
                            page_num = data_json.get("page_number")
                            img_len = len(data_json.get("image_base64", ""))
                            print(f"{Colors.OKGREEN}🖼️ [참조 이미지] {page_num}페이지 썸네일 수신 완료 (데이터 크기: {img_len} bytes){Colors.ENDC}")
                            
                        elif event_type == "answer":
                            content = data_json.get("content", "")
                            # 답변은 한 글자/단어 단위로 청킹되어 실시간 스트리밍되므로 줄바꿈 없이 출력
                            sys.stdout.write(content)
                            sys.stdout.flush()
                            
                        elif event_type == "error":
                            content = data_json.get("content", "")
                            print(f"\n{Colors.FAIL}❌ [서버 에러] {content}{Colors.ENDC}")
                            
                        elif event_type == "done":
                            print(f"\n{Colors.BOLD}[SSE STREAM END]{Colors.ENDC}\n")
                            
                    except json.JSONDecodeError:
                        print(f"{Colors.WARNING}⚠️ JSON 파싱 실패: {line}{Colors.ENDC}")
        
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ 테스트 실행 중 치명적 오류 발생: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 4. Clean up - 생성했던 테스트 문서 삭제
        if document_id and not args.no_cleanup:
            print(f"{Colors.OKBLUE}Step 4. 테스트 데이터 정리 중 (Document ID: {document_id})...{Colors.ENDC}")
            try:
                del_res = client.delete(f"/documents/{document_id}")
                if del_res.status_code == 200:
                    print(f"{Colors.OKGREEN}✅ 테스트 데이터 정리 완료.{Colors.ENDC}")
                else:
                    print(f"{Colors.FAIL}❌ 정리 실패 (HTTP {del_res.status_code}): {del_res.text}{Colors.ENDC}")
            except Exception as ex:
                print(f"{Colors.FAIL}❌ 정리 API 호출 오류: {ex}{Colors.ENDC}")
        elif document_id:
            print(f"{Colors.WARNING}⚠️ --no-cleanup 옵션에 따라 테스트 데이터를 서버에 남겨둡니다. (ID: {document_id}){Colors.ENDC}")
            
    client.close()

if __name__ == "__main__":
    main()
