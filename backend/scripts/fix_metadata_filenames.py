#!/usr/bin/env python3
import os
import sys
import re

# 백엔드 패키지 경로를 sys.path에 추가하여 app 모듈을 불러올 수 있도록 설정
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services import metadata_service
from app.utils.logger import logger

def run_migration():
    print("🔄 기존 메타데이터 비정상 문서명(filename) 복구 마이그레이션 시작...")
    
    # 노이즈 패턴 정의 (임시 제목 찌꺼기 감지)
    bad_title_pattern = re.compile(
        r"^(microsoft word\s*-\s*)"
        r"|^(한글\s*-\s*)"
        r"|^(adobe indesign\s*)"
        r"|untitled|document|cover|제목\s*없음|작업\s*일지"
        r"|\.(doc|docx|pdf|cdr|xls|xlsx|ppt|pptx|hwp|png|jpg)$",
        re.IGNORECASE
    )
    
    # 1. 모든 문서 조회
    docs = metadata_service.get_all_documents()
    print(f"총 {len(docs)}개의 문서를 조회했습니다.")
    
    fixed_count = 0
    
    for doc in docs:
        doc_id = doc.get("document_id")
        current_name = doc.get("filename", "")
        original_name = doc.get("original_filename", "")
        
        if not doc_id:
            continue
            
        # 현재 이름이 비정상 패턴에 부합하거나 비어있다면 원래 파일명으로 복구
        if not current_name or bad_title_pattern.search(current_name):
            # original_name에서 확장자 제거
            new_name = original_name
            if new_name.lower().endswith(".pdf"):
                new_name = new_name[:-4]
            
            if not new_name:
                new_name = "이름없음"
                
            print(f"🔧 복구 대상 발견! [ID: {doc_id}]")
            print(f"   기존 이름: '{current_name}'")
            print(f"   변경할 이름: '{new_name}' (원본 파일명: '{original_name}')")
            
            # 메타데이터 업데이트 실행 (로컬/GCS에 자동 동기화됨)
            try:
                metadata_service.update_document_metadata(doc_id, {"filename": new_name})
                print(f"   ✅ [ID: {doc_id}] 메타데이터 복구 성공!")
                fixed_count += 1
            except Exception as e:
                print(f"   ❌ [ID: {doc_id}] 메타데이터 업데이트 중 오류 발생: {e}")
                
    print(f"\n🏁 마이그레이션 완료! 총 {fixed_count}개의 문서명이 정상 복구되었습니다.")

if __name__ == "__main__":
    run_migration()
