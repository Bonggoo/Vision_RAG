/**
 * Sidebar 공용 헬퍼 — 순수 함수 모음. 정렬/표시명 규칙만 담당한다.
 */

const UNCLASSIFIED = "미분류";

/** 정렬·표시명 계산에 필요한 최소 필드만 요구한다 (Document 전체를 강제하지 않음) */
type NamedDoc = { filename: string; original_filename?: string };
type DatedDoc = { uploaded_at?: string };

/** PDF 메타데이터 찌꺼기("Microsoft Word - ...", "Untitled" 등)를 걸러내고 읽을 만한 제목을 고른다 */
export const getDisplayFilename = (doc: NamedDoc): string => {
  const badTitlePattern =
    /^(microsoft word\s*-\s*)|^(한글\s*-\s*)|^(adobe indesign\s*)|untitled|document|cover|제목\s*없음|\.(doc|docx|pdf|cdr|xls|xlsx|ppt|pptx|hwp|png|jpg)$/i;

  if (doc.filename && badTitlePattern.test(doc.filename) && doc.original_filename) {
    return doc.original_filename.replace(
      /\.(pdf|docx?|pptx?|xlsx?|txt|md|png|jpe?g|webp|bmp)$/i,
      ""
    );
  }
  return doc.filename;
};

const isKoreanStart = (str: string): boolean => {
  if (!str) return false;
  return /[\u3130-\u318F\uAC00-\uD7A3]/.test(str.trim().charAt(0));
};

/** 사전식 오름차순. 미분류는 맨 뒤, 한글 그룹은 영문 뒤에 온다. */
export const sortByName = (a: string, b: string): number => {
  if (a === UNCLASSIFIED) return 1;
  if (b === UNCLASSIFIED) return -1;

  const aIsKo = isKoreanStart(a);
  const bIsKo = isKoreanStart(b);
  if (aIsKo !== bIsKo) return aIsKo ? 1 : -1;

  return a.localeCompare(b, "ko", { sensitivity: "base", numeric: true });
};

const toTime = (doc: DatedDoc): number =>
  doc.uploaded_at ? new Date(doc.uploaded_at).getTime() : 0;

/** 업로드 최신순 */
export const sortByDate = (a: DatedDoc, b: DatedDoc): number => toTime(b) - toTime(a);

/** 그룹 정렬용 — 그룹 안에서 가장 최근 업로드 시각 */
export const getLatestDateInDocs = (docs: DatedDoc[]): number =>
  docs.length === 0 ? 0 : Math.max(...docs.map(toTime));
