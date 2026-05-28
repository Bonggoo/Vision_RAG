import asyncio
import os
import hashlib
import json
import fitz

# FastAPI 환경 설정을 위해 backend 폴더를 path에 추가
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# .env 환경 변수 로드
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.config import settings
from app.services import metadata_service
from app.services.agent_service import extract_document_metadata_with_gemini
from app.services.pdf_service import extract_pages_as_pdf

async def migrate_documents():
    print("🚀 기존 업로드 문서 메타데이터 마이그레이션 시작...")
    
    # 1. 모든 문서 조회
    docs = metadata_service.get_all_documents()
    total_docs = len(docs)
    print(f"📦 총 {total_docs}개의 문서가 검색되었습니다.")
    
    success_count = 0
    skipped_count = 0
    
    for idx, doc in enumerate(docs, 1):
        doc_id = doc.get("document_id")
        filename = doc.get("filename")
        original_filename = doc.get("original_filename")
        
        print(f"\n──────────────────────────────────────────────────")
        print(f"🔄 [{idx}/{total_docs}] 문서 마이그레이션 진행 중...")
        print(f"   - ID: {doc_id}")
        print(f"   - 제목: {filename}")
        print(f"   - 원본 파일명: {original_filename}")
        
        pdf_path = metadata_service.get_document_path(doc_id)
        if not pdf_path or not os.path.exists(pdf_path):
            print(f"   ❌ 오류: PDF 파일을 찾을 수 없습니다. (경로: {pdf_path})")
            continue
            
        updates = {}
        
        # A. SHA-256 해시 계산
        file_hash = doc.get("file_hash")
        if not file_hash:
            try:
                with open(pdf_path, "rb") as f:
                    content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()
                updates["file_hash"] = file_hash
                print(f"   ✅ SHA-256 해시 생성 완료: {file_hash[:10]}...")
            except Exception as e:
                print(f"   ❌ 해시 생성 실패: {e}")
        else:
            print(f"   ℹ️ 기존 SHA-256 해시 보유 중: {file_hash[:10]}...")
            
        # B. AI 기반 자동 분류 및 제목 보강
        manufacturer = doc.get("manufacturer")
        model_series = doc.get("model_series")
        doc_type = doc.get("doc_type")
        
        # 이미 제조사 및 모델 정보가 모두 채워져 있다면 스킵
        if manufacturer and model_series:
            print(f"   ℹ️ 이미 분류 완료된 문서입니다. (제조사: {manufacturer}, 모델: {model_series})")
        else:
            print(f"   🔍 AI 분류 시작 (Gemini Vision 분석)...")
            try:
                fitz_doc = fitz.open(pdf_path)
                if fitz_doc.page_count > 0:
                    first_page_pdf = extract_pages_as_pdf(fitz_doc, 0, 0)
                    fitz_doc.close()
                    
                    # Gemini API 호출
                    classification = await extract_document_metadata_with_gemini(first_page_pdf)
                    
                    if classification:
                        print(f"   ✨ Gemini 분석 성공:")
                        print(f"     - 추출 제조사: {classification.get('manufacturer')}")
                        print(f"     - 추출 모델 시리즈: {classification.get('model_series')}")
                        print(f"     - 추출 문서 유형: {classification.get('doc_type')}")
                        print(f"     - 추천 공식 제목: {classification.get('title')}")
                        
                        # 값이 비어있을 때만 업데이트 또는 AI 추천값으로 덮어쓰기 선택
                        # 기존 문서들의 파일명(filename)이 이상한 경우, AI가 찾아준 title로 갱신합니다.
                        if classification.get("title") and (not filename or len(filename) < 5 or filename == original_filename):
                            updates["filename"] = classification["title"]
                            print(f"     * 문서 제목을 공식 제목으로 갱신합니다: {filename} -> {classification['title']}")
                            
                        if classification.get("manufacturer"):
                            updates["manufacturer"] = classification["manufacturer"]
                        if classification.get("model_series"):
                            updates["model_series"] = classification["model_series"]
                        if classification.get("doc_type"):
                            updates["doc_type"] = classification["doc_type"]
                    else:
                        print("   ⚠️ Gemini 분석 결과가 비어있습니다. 로컬 기본값 적용.")
                        updates["manufacturer"] = None
                        updates["model_series"] = None
                        updates["doc_type"] = None
                else:
                    fitz_doc.close()
                    print("   ❌ 오류: PDF 페이지가 존재하지 않습니다.")
            except Exception as e:
                print(f"   ❌ Gemini 분석 및 분류 실패: {e}")
                
        # C. 메타데이터 업데이트 실행
        if updates:
            try:
                updated = metadata_service.update_document_metadata(doc_id, updates)
                if updated:
                    print(f"   🎉 메타데이터 업데이트 성공! ({list(updates.keys())} 필드 변경)")
                    success_count += 1
                else:
                    print("   ❌ 메타데이터 업데이트 실패 (update_document_metadata 실패)")
            except Exception as e:
                print(f"   ❌ 메타데이터 파일 쓰기 실패: {e}")
        else:
            print("   ℹ️ 변경할 메타데이터가 없어 마이그레이션을 건너뜁니다.")
            skipped_count += 1
            
    print(f"\n🏁 마이그레이션 완료!")
    print(f"✅ 성공적으로 업데이트된 문서: {success_count}개")
    print(f"ℹ️ 건너뛴 문서 (이미 완료됨): {skipped_count}개")

if __name__ == "__main__":
    asyncio.run(migrate_documents())
