"""
document_conversion 서비스 단위 테스트.

비-PDF 문서(Office/텍스트/마크다운/이미지)를 업로드 시점에 PDF로 정규화하는
변환 계층을 검증합니다. 변환 결과는 기존 파이프라인(build_toc, Phase 1~3)이
그대로 소비할 수 있는 유효한 PDF 바이트여야 합니다.
"""
import asyncio
import os
import shutil
import zipfile

import fitz
import pytest

from app.services import document_conversion as dc
from app.services.document_conversion import ConversionError


# ── 카테고리 판별 ────────────────────────────────────────────────────────────

class TestGetCategory:
    def test_pdf(self):
        assert dc.get_category("manual.pdf") == "pdf"

    def test_office_formats(self):
        assert dc.get_category("spec.docx") == "office"
        assert dc.get_category("deck.pptx") == "office"
        assert dc.get_category("sheet.xlsx") == "office"
        assert dc.get_category("legacy.doc") == "office"
        assert dc.get_category("legacy.ppt") == "office"
        assert dc.get_category("legacy.xls") == "office"

    def test_text_formats(self):
        assert dc.get_category("notes.txt") == "text"
        assert dc.get_category("README.md") == "text"

    def test_image_formats(self):
        assert dc.get_category("photo.jpg") == "image"
        assert dc.get_category("photo.jpeg") == "image"
        assert dc.get_category("scan.png") == "image"
        assert dc.get_category("pic.webp") == "image"
        assert dc.get_category("pic.bmp") == "image"

    def test_unsupported_returns_none(self):
        assert dc.get_category("virus.exe") is None
        assert dc.get_category("archive.zip") is None
        assert dc.get_category("noextension") is None
        assert dc.get_category("문서.hwp") is None

    def test_case_insensitive(self):
        assert dc.get_category("REPORT.DOCX") == "office"
        assert dc.get_category("Manual.PDF") == "pdf"


# ── 원본 blob 파일명 규약 ────────────────────────────────────────────────────

class TestSourceBlobFilename:
    def test_pdf_keeps_canonical_name(self):
        assert dc.source_blob_filename("manual.pdf") == "original.pdf"

    def test_non_pdf_gets_source_prefix(self):
        assert dc.source_blob_filename("spec.docx") == "source_original.docx"
        assert dc.source_blob_filename("notes.txt") == "source_original.txt"
        assert dc.source_blob_filename("photo.jpg") == "source_original.jpg"

    def test_extension_normalized_to_lowercase(self):
        assert dc.source_blob_filename("REPORT.DOCX") == "source_original.docx"


# ── Content-Type 매핑 (GCS Signed URL 서명 고정용) ──────────────────────────

class TestContentType:
    def test_known_types(self):
        assert dc.content_type_for("a.pdf") == "application/pdf"
        assert dc.content_type_for("a.docx") == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert dc.content_type_for("a.xlsx") == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert dc.content_type_for("a.png") == "image/png"
        assert dc.content_type_for("a.jpg") == "image/jpeg"
        assert dc.content_type_for("a.txt") == "text/plain"

    def test_unsupported_returns_none(self):
        assert dc.content_type_for("a.exe") is None


# ── 변환 헬퍼 픽스처 ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_docs(tmp_path):
    return str(tmp_path)


def _make_minimal_docx(path: str, paragraphs: list[str]):
    """python-docx 없이 zipfile로 최소 유효 docx를 생성합니다."""
    ct = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    docxml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", docxml)


def _open_pdf(pdf_bytes: bytes) -> fitz.Document:
    assert isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 0
    return fitz.open(stream=pdf_bytes, filetype="pdf")


# ── 이미지 → PDF ────────────────────────────────────────────────────────────

class TestImageConversion:
    def test_png_to_single_page_pdf(self, tmp_docs):
        # fitz로 작은 PNG 생성
        src = os.path.join(tmp_docs, "scan.png")
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 80))
        pix.clear_with(200)
        pix.save(src)

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "scan.png"))
        doc = _open_pdf(pdf_bytes)
        assert doc.page_count == 1

    def test_garbage_named_png_rejected(self, tmp_docs):
        src = os.path.join(tmp_docs, "fake.png")
        with open(src, "wb") as f:
            f.write(b"this is not an image at all")
        with pytest.raises(ConversionError):
            asyncio.run(dc.convert_to_pdf(src, "fake.png"))


# ── 텍스트/마크다운 → PDF ───────────────────────────────────────────────────

class TestTextConversion:
    def test_korean_utf8_text(self, tmp_docs):
        src = os.path.join(tmp_docs, "notes.txt")
        content = "안전 밸브 점검 절차\n압력 게이지를 매월 확인하십시오.\n" * 3
        with open(src, "w", encoding="utf-8") as f:
            f.write(content)

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "notes.txt"))
        doc = _open_pdf(pdf_bytes)
        assert doc.page_count >= 1
        extracted = "".join(page.get_text() for page in doc)
        assert "안전 밸브 점검 절차" in extracted
        assert "압력 게이지" in extracted

    def test_korean_euckr_fallback(self, tmp_docs):
        src = os.path.join(tmp_docs, "legacy.txt")
        with open(src, "wb") as f:
            f.write("설비 점검 일지\n모터 온도 정상".encode("euc-kr"))

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "legacy.txt"))
        doc = _open_pdf(pdf_bytes)
        extracted = "".join(page.get_text() for page in doc)
        assert "설비 점검 일지" in extracted

    def test_long_text_paginates(self, tmp_docs):
        src = os.path.join(tmp_docs, "long.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("유지보수 항목 설명 라인\n" * 500)

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "long.txt"))
        doc = _open_pdf(pdf_bytes)
        assert doc.page_count >= 2

    def test_markdown_headers_become_bookmarks(self, tmp_docs):
        src = os.path.join(tmp_docs, "guide.md")
        md = (
            "# 설치 가이드\n\n본문입니다.\n\n"
            "## 전원 연결\n\n케이블을 연결합니다.\n\n"
            "## 시운전\n\n전원을 켭니다.\n"
        )
        with open(src, "w", encoding="utf-8") as f:
            f.write(md)

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "guide.md"))
        doc = _open_pdf(pdf_bytes)
        toc = doc.get_toc()
        titles = [t[1] for t in toc]
        assert "설치 가이드" in titles
        assert "전원 연결" in titles
        assert "시운전" in titles
        # 헤더 레벨이 보존되어야 함
        levels = {t[1]: t[0] for t in toc}
        assert levels["설치 가이드"] == 1
        assert levels["전원 연결"] == 2


# ── Office → PDF (LibreOffice 필요) ─────────────────────────────────────────

needs_soffice = pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice(soffice)가 설치되지 않음"
)


@needs_soffice
class TestOfficeConversion:
    def test_docx_korean(self, tmp_docs):
        src = os.path.join(tmp_docs, "spec.docx")
        _make_minimal_docx(src, ["안전 밸브 점검 매뉴얼", "1장. 압력 게이지 확인"])

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "spec.docx"))
        doc = _open_pdf(pdf_bytes)
        assert doc.page_count >= 1
        extracted = doc[0].get_text()
        assert "안전 밸브 점검 매뉴얼" in extracted

    def test_corrupt_docx_raises(self, tmp_docs):
        src = os.path.join(tmp_docs, "broken.docx")
        with open(src, "wb") as f:
            f.write(b"not a real docx file")
        with pytest.raises(ConversionError):
            asyncio.run(dc.convert_to_pdf(src, "broken.docx"))


# ── xlsx 전처리 (가로 폭 맞춤) ───────────────────────────────────────────────

class TestXlsxPreprocess:
    def test_fit_to_width_forced(self, tmp_docs):
        openpyxl = pytest.importorskip("openpyxl")
        src = os.path.join(tmp_docs, "wide.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        for col in range(1, 30):
            ws.cell(row=1, column=col, value=f"컬럼{col}")
        wb.save(src)

        dc._preprocess_xlsx(src)

        wb2 = openpyxl.load_workbook(src)
        ws2 = wb2.active
        assert ws2.page_setup.fitToWidth == 1
        assert ws2.page_setup.fitToHeight == 0
        assert ws2.sheet_properties.pageSetUpPr.fitToPage is True


# ── 디스패처 공통 동작 ───────────────────────────────────────────────────────

class TestDispatcher:
    def test_unsupported_extension_raises(self, tmp_docs):
        src = os.path.join(tmp_docs, "malware.exe")
        with open(src, "wb") as f:
            f.write(b"MZ")
        with pytest.raises(ConversionError):
            asyncio.run(dc.convert_to_pdf(src, "malware.exe"))

    def test_pdf_passthrough(self, tmp_docs):
        src = os.path.join(tmp_docs, "already.pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(src)

        pdf_bytes = asyncio.run(dc.convert_to_pdf(src, "already.pdf"))
        assert _open_pdf(pdf_bytes).page_count == 1

    def test_missing_file_raises(self, tmp_docs):
        with pytest.raises(ConversionError):
            asyncio.run(dc.convert_to_pdf(os.path.join(tmp_docs, "ghost.docx"), "ghost.docx"))
