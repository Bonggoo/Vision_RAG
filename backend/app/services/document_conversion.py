"""
비-PDF 문서 → PDF 정규화 변환 서비스.

업로드 시점에 모든 지원 포맷(Office/텍스트/마크다운/이미지)을 PDF로 변환하여
기존 관례(users/{owner}/{doc_id}/original.pdf)대로 저장합니다. 이후 ToC 추출,
Phase 1~3 파이프라인, 썸네일 등 PDF 전용 코드가 무수정으로 동작합니다.

원본 파일은 source_original{ext}로 함께 보관되어 다운로드 시 원본을 제공합니다.
"""
import asyncio
import io
import os
import subprocess
import tempfile
import uuid
from typing import Optional

import fitz

from app.utils.logger import logger


class ConversionError(Exception):
    """PDF 변환 실패. 메시지는 사용자에게 노출되는 error_message로 사용됩니다."""


# 확장자 → 카테고리 ("pdf" | "office" | "text" | "image")
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "office", ".doc": "office",
    ".pptx": "office", ".ppt": "office",
    ".xlsx": "office", ".xls": "office",
    ".txt": "text", ".md": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".webp": "image", ".bmp": "image",
}

# 확장자 → MIME (GCS Signed URL은 서명 시점의 content-type과 PUT 헤더가
# 정확히 일치해야 하므로, 브라우저의 file.type 대신 이 맵을 단일 소스로 사용)
CONTENT_TYPE_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Cloud Run 인스턴스(--concurrency=8, --memory=2Gi)에서 soffice 프로세스가
# 동시에 몰리면 메모리 초과 위험이 있어 동시 변환 수를 제한합니다.
_office_semaphore = asyncio.Semaphore(2)

_OFFICE_TIMEOUT_SECONDS = 300


def get_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def get_category(filename: str) -> Optional[str]:
    """파일명의 확장자로 변환 카테고리를 판별합니다. 미지원이면 None."""
    return SUPPORTED_EXTENSIONS.get(get_extension(filename))


def content_type_for(filename: str) -> Optional[str]:
    return CONTENT_TYPE_MAP.get(get_extension(filename))


def source_blob_filename(filename: str) -> str:
    """
    업로드 원본이 저장될 blob 파일명.
    PDF는 기존 관례(original.pdf) 그대로, 비-PDF는 source_original{ext}에 두고
    변환 결과가 original.pdf 자리를 차지합니다.
    """
    ext = get_extension(filename)
    if ext == ".pdf":
        return "original.pdf"
    return f"source_original{ext}"


def source_blob_name_from_format(source_format: str) -> str:
    """metadata의 source_format(예: 'docx')으로 원본 blob 파일명을 복원합니다."""
    return f"source_original.{source_format}"


# ── 시그니처(매직 바이트) 검증 ────────────────────────────────────────────────

def _check_signature(source_path: str, filename: str, category: str):
    """확장자와 실제 파일 내용의 불일치를 조기에 잡습니다. (text는 검증 불가)"""
    with open(source_path, "rb") as f:
        head = f.read(8)

    if category == "pdf" and not head.startswith(b"%PDF"):
        raise ConversionError("PDF 파일이 아닙니다. 파일이 손상되었거나 확장자가 잘못되었습니다.")

    if category == "office":
        ext = get_extension(filename)
        if ext in (".docx", ".pptx", ".xlsx"):
            if not head.startswith(b"PK\x03\x04"):
                raise ConversionError("파일 내용이 확장자와 일치하지 않습니다. 올바른 Office 문서인지 확인해 주세요.")
        else:  # .doc / .ppt / .xls (OLE2)
            if not head.startswith(b"\xd0\xcf\x11\xe0"):
                raise ConversionError("파일 내용이 확장자와 일치하지 않습니다. 올바른 Office 문서인지 확인해 주세요.")

    if category == "image":
        import filetype
        kind = filetype.guess(source_path)
        if kind is None or not kind.mime.startswith("image/"):
            raise ConversionError("이미지 파일이 아닙니다. 파일이 손상되었거나 확장자가 잘못되었습니다.")


# ── 디스패처 ────────────────────────────────────────────────────────────────

async def convert_to_pdf(source_path: str, filename: str) -> bytes:
    """
    원본 파일을 PDF 바이트로 변환합니다. 실패 시 ConversionError.
    PDF 입력은 그대로 읽어 반환합니다(방어적 패스스루).
    """
    category = get_category(filename)
    if category is None:
        raise ConversionError(f"지원하지 않는 파일 형식입니다: {get_extension(filename) or filename}")

    if not os.path.isfile(source_path):
        raise ConversionError("원본 파일을 찾을 수 없습니다.")

    _check_signature(source_path, filename, category)

    logger.info(f"📄 PDF 변환 시작 ({category}): {filename}")
    try:
        if category == "pdf":
            with open(source_path, "rb") as f:
                return f.read()
        if category == "image":
            return await asyncio.to_thread(_convert_image, source_path)
        if category == "text":
            is_markdown = get_extension(filename) == ".md"
            return await asyncio.to_thread(_convert_text, source_path, is_markdown)
        # office
        return await _convert_office(source_path, filename)
    except ConversionError:
        raise
    except Exception as e:
        logger.error(f"❌ PDF 변환 실패 ({filename}): {e}")
        raise ConversionError(f"PDF 변환에 실패했습니다: {e}")


# ── 이미지 → 1페이지 PDF ────────────────────────────────────────────────────

def _convert_image(source_path: str) -> bytes:
    # 폰카 사진의 EXIF 회전 정보를 픽셀에 반영한 뒤 PDF로 래핑
    try:
        from PIL import Image, ImageOps
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_bytes = buf.getvalue()
    except ImportError:
        with open(source_path, "rb") as f:
            image_bytes = f.read()

    img_doc = fitz.open(stream=image_bytes)
    pdf_bytes = img_doc.convert_to_pdf()
    img_doc.close()
    return pdf_bytes


# ── 텍스트/마크다운 → PDF (PyMuPDF 직접 렌더링) ─────────────────────────────
# LibreOffice의 텍스트 임포트 필터는 headless 모드에서 인코딩 자동 감지가
# 불안정하므로(레거시 EUC-KR 파일 등) PyMuPDF 내장 CJK 폰트로 직접 렌더링합니다.
# 마크다운 헤더(#/##/###)는 PDF 북마크로 주입되어 build_toc Case A가 그대로 동작합니다.

_PAGE_RECT = fitz.paper_rect("a4")
_MARGIN = 50.0
_BODY_SIZE = 11.0
_HEADING_SIZES = {1: 20.0, 2: 16.0, 3: 13.0}
_LINE_GAP = 1.45


def _decode_text_file(source_path: str) -> str:
    with open(source_path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            return str(best)
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def _wrap_line(font: fitz.Font, text: str, fontsize: float, max_width: float) -> list[str]:
    """한국어(공백 없는 장문 포함)를 폭 기준으로 그리디 줄바꿈합니다."""
    if not text:
        return [""]
    lines, current = [], ""
    for ch in text:
        if font.text_length(current + ch, fontsize=fontsize) > max_width and current:
            lines.append(current)
            current = ch.lstrip() if ch == " " else ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def _convert_text(source_path: str, is_markdown: bool) -> bytes:
    text = _decode_text_file(source_path)
    font = fitz.Font("cjk")  # Droid Sans Fallback — 한글/한자/일본어 커버, 번들 폰트 불필요

    doc = fitz.open()
    toc: list[list] = []
    max_width = _PAGE_RECT.width - 2 * _MARGIN

    page = doc.new_page(width=_PAGE_RECT.width, height=_PAGE_RECT.height)
    writer = fitz.TextWriter(page.rect)
    y = _MARGIN

    def flush_page():
        nonlocal page, writer, y
        writer.write_text(page)
        page = doc.new_page(width=_PAGE_RECT.width, height=_PAGE_RECT.height)
        writer = fitz.TextWriter(page.rect)
        y = _MARGIN

    def emit(line: str, fontsize: float):
        nonlocal y
        line_height = fontsize * _LINE_GAP
        for wrapped in _wrap_line(font, line, fontsize, max_width):
            if y + line_height > _PAGE_RECT.height - _MARGIN:
                flush_page()
            writer.append((_MARGIN, y + fontsize), wrapped, font=font, fontsize=fontsize)
            y += line_height

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading_level = 0
        if is_markdown and line.lstrip().startswith("#"):
            stripped = line.lstrip()
            hashes = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[hashes:].strip()
            if 1 <= hashes <= 6 and title:
                heading_level = min(hashes, 3)
                toc.append([heading_level, title, doc.page_count])
                y += _HEADING_SIZES[heading_level] * 0.6  # 헤더 위 여백
                emit(title, _HEADING_SIZES[heading_level])
                continue
        if not line:
            y += _BODY_SIZE * 0.8  # 문단 간격
            continue
        emit(line, _BODY_SIZE)

    writer.write_text(page)

    if is_markdown and toc:
        doc.set_toc(toc)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ── Office → PDF (LibreOffice headless) ─────────────────────────────────────

def _preprocess_xlsx(source_path: str):
    """
    xlsx의 각 시트를 '가로 폭 맞춤' 인쇄 설정으로 강제합니다.
    사용자가 인쇄 영역을 설정하지 않은 넓은 시트가 수십 페이지로
    찢어져 변환되는 것을 방지합니다. openpyxl이 없거나 실패해도 변환은 계속합니다.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(source_path)
        for ws in wb.worksheets:
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 0
        wb.save(source_path)
    except Exception as e:
        logger.warning(f"⚠️ xlsx 가로 폭 맞춤 전처리 건너뜀(비차단): {e}")


def _run_soffice(source_path: str, out_dir: str) -> str:
    """soffice 서브프로세스를 실행하고 생성된 PDF 경로를 반환합니다."""
    # 호출별 격리 프로필: 동시 변환 시 사용자 프로필 락 경합/행 방지
    profile_dir = os.path.join(tempfile.gettempdir(), f"lo_profile_{uuid.uuid4().hex}")
    cmd = [
        "soffice", "--headless", "--norestore",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to", "pdf", "--outdir", out_dir, source_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_OFFICE_TIMEOUT_SECONDS
    )
    base = os.path.splitext(os.path.basename(source_path))[0]
    pdf_path = os.path.join(out_dir, f"{base}.pdf")
    if result.returncode != 0 or not os.path.isfile(pdf_path):
        # 원본 stderr/stdout에는 컨테이너 내부 경로가 섞일 수 있어 서버 로그로만 남기고,
        # 사용자에게는 일반 메시지만 반환한다 (audit M-4).
        detail = (result.stderr or result.stdout or "").strip()[-300:]
        logger.error(f"❌ soffice 변환 실패 (rc={result.returncode}): {detail}")
        raise ConversionError("Office 문서 변환에 실패했습니다. 파일이 손상되었거나 지원되지 않는 서식일 수 있습니다.")
    return pdf_path


async def _convert_office(source_path: str, filename: str) -> bytes:
    if get_extension(filename) == ".xlsx":
        await asyncio.to_thread(_preprocess_xlsx, source_path)

    async with _office_semaphore:
        with tempfile.TemporaryDirectory(prefix="lo_convert_") as out_dir:
            pdf_path = await asyncio.to_thread(_run_soffice, source_path, out_dir)
            with open(pdf_path, "rb") as f:
                return f.read()
