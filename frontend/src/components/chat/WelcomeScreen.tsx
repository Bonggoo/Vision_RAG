"use client";

import React, { useRef } from "react";
import { ArrowRight, Loader2, Upload } from "lucide-react";
import { useDocumentStore } from "@/store/useDocumentStore";
import { processUploadFiles } from "@/lib/upload";
import { UPLOAD_ACCEPT_ATTR } from "@/lib/fileTypes";
import SparkleLogo from "@/components/layout/SparkleLogo";

const EXAMPLE_PROMPTS = [
  "서보 2051 알람 설명",
  "배터리 교체 주기와 방법",
  "원점 복귀(Homing) 설정 절차",
  "통신 에러 타임아웃 해결법",
];

const ONBOARDING_STEPS = [
  { step: "1", title: "매뉴얼 업로드", desc: "PDF·Word·Excel·이미지" },
  { step: "2", title: "질문 입력", desc: "평소 말하듯 물어보기" },
  { step: "3", title: "근거와 함께 답변", desc: "출처 페이지까지 표시" },
];

interface WelcomeScreenProps {
  onAskExample: (question: string) => void;
}

/**
 * 대화가 비어 있을 때의 첫 화면.
 * 문서 보유 여부에 따라 온보딩(첫 사용자) ↔ 예시 질문(재방문)으로 분기한다.
 */
export default function WelcomeScreen({ onAskExample }: WelcomeScreenProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    documents,
    hasFetched,
    uploadDocuments,
    fetchDocuments,
    isUploading,
    uploadingIndex,
    uploadTotal,
    uploadProgress,
  } = useDocumentStore();

  const readyDocs = documents.filter((d) => d.status !== "analyzing" && d.status !== "error");
  const analyzingCount = documents.filter((d) => d.status === "analyzing").length;
  const hasReadyDocs = readyDocs.length > 0;

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    await processUploadFiles(files, uploadDocuments, fetchDocuments);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const openFilePicker = () => fileInputRef.current?.click();

  return (
    <div className="flex-1 flex flex-col justify-center items-center px-6 py-10">
      <input
        type="file"
        accept={UPLOAD_ACCEPT_ATTR}
        multiple
        ref={fileInputRef}
        onChange={handleUpload}
        className="hidden"
      />

      <div className="w-full max-w-xl text-center animate-slide-up">
        <SparkleLogo className="w-9 h-9 mx-auto mb-5 text-primary" />

        <h2 className="font-display text-[28px] md:text-[34px] font-normal tracking-tight mb-2.5">
          무엇을 찾아드릴까요?
        </h2>
        <p className="text-[14px] text-muted-foreground leading-relaxed text-balance">
          {!hasFetched || hasReadyDocs
            ? "등록된 산업용 매뉴얼에서 필요한 내용을 찾아 근거와 함께 알려드립니다."
            : "매뉴얼을 올리면 AI가 대신 읽고 찾아드립니다. 세 단계면 시작할 수 있어요."}
        </p>

        {!hasFetched ? (
          /* 분기 확정 전 스켈레톤 — 온보딩↔예시질문 화면이 번갈아 깜빡이는 것을 방지 */
          <div data-testid="welcome-skeleton" className="mt-8 space-y-2" aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-11 rounded-lg animate-shimmer" />
            ))}
          </div>
        ) : hasReadyDocs ? (
          <>
            <ul className="mt-8 space-y-2 text-left">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <li key={prompt}>
                  <button
                    onClick={() => onAskExample(prompt)}
                    className="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-lg
                      border border-border bg-[var(--surface)] text-[14px]
                      hover:border-border-strong hover:bg-accent transition-colors group"
                  >
                    <span>{prompt}</span>
                    <ArrowRight className="w-4 h-4 text-muted-foreground/50 group-hover:text-foreground transition-colors shrink-0" />
                  </button>
                </li>
              ))}
            </ul>

            <button
              onClick={openFilePicker}
              disabled={isUploading}
              className="mt-6 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              {isUploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              {isUploading
                ? `업로드 중 ${uploadingIndex + 1}/${uploadTotal}`
                : `매뉴얼 추가 · 현재 ${readyDocs.length}개`}
            </button>
          </>
        ) : (
          <div className="mt-8 space-y-4">
            <ol className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-left">
              {ONBOARDING_STEPS.map((s) => (
                <li
                  key={s.step}
                  className="px-4 py-3.5 rounded-lg border border-border bg-[var(--surface)]"
                >
                  <span className="block text-[11px] font-medium text-primary mb-1">
                    {s.step}
                  </span>
                  <span className="block text-[13.5px] font-medium">{s.title}</span>
                  <span className="block text-[12px] text-muted-foreground mt-0.5">
                    {s.desc}
                  </span>
                </li>
              ))}
            </ol>

            {analyzingCount > 0 && (
              <p className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border bg-[var(--muted)] text-[13px] text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                매뉴얼 {analyzingCount}개를 분석 중이에요. 잠시 후 질문할 수 있어요.
              </p>
            )}

            <button
              onClick={openFilePicker}
              disabled={isUploading}
              className="btn-primary w-full flex items-center justify-center gap-2 py-3 px-5 rounded-lg text-[14px]"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  업로드 중 {uploadingIndex + 1}/{uploadTotal} · {uploadProgress}%
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  {analyzingCount > 0 ? "매뉴얼 더 올리기" : "매뉴얼 업로드하고 시작하기"}
                </>
              )}
            </button>
            <p className="text-[12px] text-muted-foreground/70">
              사이드바에 파일을 끌어다 놓아도 됩니다.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
