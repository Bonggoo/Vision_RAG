/**
 * 업로드 지원 파일 형식 단일 소스.
 * 백엔드 app/services/document_conversion.py 의 SUPPORTED_EXTENSIONS 와 동기화되어야 합니다.
 * 비-PDF 형식은 서버에서 PDF로 변환된 후 기존 파이프라인(ToC 추출 → Vision 분석)을 그대로 탑니다.
 */
export const SUPPORTED_UPLOAD_EXTENSIONS = [
  ".pdf",
  ".docx", ".doc",
  ".pptx", ".ppt",
  ".xlsx", ".xls",
  ".txt", ".md",
  ".png", ".jpg", ".jpeg", ".webp", ".bmp",
] as const;

/** <input type="file" accept=...> 용 문자열 */
export const UPLOAD_ACCEPT_ATTR = SUPPORTED_UPLOAD_EXTENSIONS.join(",");

export const UNSUPPORTED_FORMAT_MESSAGE =
  "지원하지 않는 파일 형식입니다. (지원: PDF, Word, Excel, PowerPoint, 텍스트/마크다운, 이미지)";

/** 확장자 기준 지원 여부 검사 (브라우저 MIME은 OS별로 불안정하므로 확장자를 기준으로 함) */
export function isSupportedUploadFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return SUPPORTED_UPLOAD_EXTENSIONS.some((ext) => name.endsWith(ext));
}
