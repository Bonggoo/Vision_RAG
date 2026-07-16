/**
 * Sidebar 공용 헬퍼 (M5 분해)
 * 기존 Sidebar.tsx 상단에 있던 순수 함수들을 그대로 옮긴 것. 로직 변경 없음.
 */

// PDF 메타데이터 찌꺼기 등을 제외하고 가독성 있는 파일명을 결정하는 헬퍼 함수
export const getDisplayFilename = (doc: any): string => {
  const badTitlePattern = /^(microsoft word\s*-\s*)|^(한글\s*-\s*)|^(adobe indesign\s*)|untitled|document|cover|제목\s*없음|\.(doc|docx|pdf|cdr|xls|xlsx|ppt|pptx|hwp|png|jpg)$/i;

  if (doc.filename && badTitlePattern.test(doc.filename)) {
    if (doc.original_filename) {
      return doc.original_filename.replace(/\.(pdf|docx?|pptx?|xlsx?|txt|md|png|jpe?g|webp|bmp)$/i, "");
    }
  }
  return doc.filename;
};

// 문자열의 첫 글자가 한글인지 여부를 판별하는 헬퍼 함수
const isKoreanStart = (str: string): boolean => {
  if (!str) return false;
  const firstChar = str.trim().charAt(0);
  return /[\u3130-\u318F\uAC00-\uD7A3]/.test(firstChar);
};

// 한글 가나다 및 영어 ABCD 사전식 오름차순 정렬을 위한 헬퍼 함수
export const sortByName = (a: string, b: string): number => {
  if (a === "미분류") return 1;
  if (b === "미분류") return -1;

  const aIsKo = isKoreanStart(a);
  const bIsKo = isKoreanStart(b);

  if (aIsKo && !bIsKo) return 1;
  if (!aIsKo && bIsKo) return -1;

  return a.localeCompare(b, "ko", { sensitivity: "base", numeric: true });
};

// 업로드 날짜 기준 정렬
export const sortByDate = (a: any, b: any): number => {
  const dateA = a.uploaded_at ? new Date(a.uploaded_at).getTime() : 0;
  const dateB = b.uploaded_at ? new Date(b.uploaded_at).getTime() : 0;
  return dateB - dateA;
};

export const getLatestDateInDocs = (docs: any[]): number => {
  if (docs.length === 0) return 0;
  return Math.max(...docs.map(d => d.uploaded_at ? new Date(d.uploaded_at).getTime() : 0));
};
