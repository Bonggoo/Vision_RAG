import fitz
import os
import json

file_path = "uploads/QD77MS_위치결정_매뉴얼.pdf"

try:
    doc = fitz.open(file_path)
    print(f"Total Pages: {doc.page_count}")
    
    # 품질 검사 함수
    def is_toc_meaningful(t, total):
        if not t: return False
        if total > 100 and len(t) < (total / 100): return False
        if not any(item[0] > 1 for item in t) and len(t) < 20: return False
        return True

    # 1. 북마크(ToC) 확인
    raw_toc = doc.get_toc()
    if is_toc_meaningful(raw_toc, doc.page_count):
        print(f"\n[ToC] Found {len(raw_toc)} bookmark entries! (Case A: High Quality)")
        print("\n=== 전체 목차 내용 ===")
        for item in raw_toc:
            print(f"Level: {item[0]}, Title: '{item[1]}', Page: {item[2]}")
    else:
        if raw_toc:
            print(f"\n[ToC] Found {len(raw_toc)} entries, but QUALITY IS POOR. (Case A-1 -> Fallback to Case B)")
        else:
            print("\n[ToC] No bookmarks found.")
        
        # 2. 텍스트 추출 가능 여부 확인
        text = ""
        for i in range(min(3, doc.page_count)):
            text += doc[i].get_text()
            
        if len(text.strip()) > 50:
            print("[Text] Text is extractable. (Case B: Extracting ToC from first 15 pages using Gemini...)")
            
            # 여기서부터 미니 PDF 추출 및 Gemini 전송
            import sys
            sys.path.append('.') # import app.services 를 위해 경로 추가
            from app.services.pdf_service import extract_pages_as_pdf
            from app.services.agent_service import extract_toc_with_gemini
            
            extract_pages = min(15, doc.page_count)
            mini_pdf_bytes = extract_pages_as_pdf(doc, 0, extract_pages - 1)
            
            print(f"-> Created mini PDF with {extract_pages} pages ({len(mini_pdf_bytes)} bytes)")
            print("-> Sending to Gemini 3.1 Pro... (Please wait 10~20 seconds)")
            
            extracted_toc = extract_toc_with_gemini(mini_pdf_bytes)
            
            print(f"\n=== Gemini가 추출한 목차 (총 {len(extracted_toc)}개) ===")
            # 처음 10개와 마지막 3개만 출력하여 확인
            for i, item in enumerate(extracted_toc[:10]):
                print(f"Level: {item.get('level')}, Title: '{item.get('title')}', Page: {item.get('page')}")
            if len(extracted_toc) > 13:
                print("... (중략) ...")
                for i, item in enumerate(extracted_toc[-3:]):
                    print(f"Level: {item.get('level')}, Title: '{item.get('title')}', Page: {item.get('page')}")
            
        else:
            print("[Text] No text found. (Case C: Scanned PDF. Need User Input for ToC range)")

except Exception as e:
    print(f"Error: {e}")
