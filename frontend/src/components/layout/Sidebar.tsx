"use client";

import React, { useRef, useEffect, useState } from "react";
import {
  PlusCircle,
  MessageSquare,
  UploadCloud,
  Loader2,
  FileText,
  Trash2,
  X,
  ChevronRight,
  ChevronDown,
  Pencil,
  Check,
  Download,
  Building,
  Cpu,
  Folder,
  Search,
  AlertCircle,
  RotateCw
} from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useDocumentStore, Document } from "@/store/useDocumentStore";
import { useAuthStore } from "@/store/useAuthStore";

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  // 💡 Hydration 에러 방지: 마운트 상태 추가
  const [isMounted, setIsMounted] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession } =
    useChatStore();
  const { user } = useAuthStore();

  // 현재 로그인 사용자의 세션만 필터링 (ownerEmail 미설정 거의시 세션은 공용으로 포함)
  const mySessions = sessions.filter(
    (s) => s.ownerEmail === user?.email || !s.ownerEmail
  );
  const {
    documents,
    uploadDocuments,
    fetchDocuments,
    isUploading,
    uploadingIndex,
    uploadTotal,
    uploadProgress: storeUploadProgress, // 💡 실제 업로드 진행률 추가
    deleteDoc,
    updateDocMeta,
    downloadDoc
  } = useDocumentStore();

  // 💡 실시간 AI 분석 중인 문서 목록 필터링
  const analyzingDocuments = documents.filter((doc) => doc.status === "analyzing");

  // 드래그 앤 드롭 상태
  const [isDragging, setIsDragging] = useState(false);

  // 검색 쿼리
  const [searchQuery, setSearchQuery] = useState("");

  // 아코디언 접기/펼치기 상태 (초기에는 펼쳐진 상태 true)
  const [expandedManufacturers, setExpandedManufacturers] = useState<Record<string, boolean>>({});
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});

  // 인라인 편집 상태
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [editingMfg, setEditingMfg] = useState("");
  const [editingModel, setEditingModel] = useState("");
  const [editingName, setEditingName] = useState("");

  // 업로드 진행률 애니메이션용 상태
  const [uploadProgress, setUploadProgress] = useState(0);

  // 💡 브라우저 마운트 완료 후 렌더링
  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (isUploading && uploadTotal > 0) {
      // Zustand 스토어에 업로드 중인 실제 진행률(0~100)을 직접 반영
      setUploadProgress(storeUploadProgress);
    } else {
      setUploadProgress(0);
    }
  }, [isUploading, storeUploadProgress, uploadTotal]);

  // 15초마다 문서 목록 자동 갱신 (기기 간 상태 동기화)
  useEffect(() => {
    if (!isMounted) return; // 마운트 후에만 실행

    // 💡 안전한 window.innerWidth 접근 (브라우저 환경 검증)
    const isDesktop = () => {
      if (typeof window === "undefined") return false;
      return window.innerWidth >= 768;
    };

    if (!isDesktop() && !isOpen) return;

    fetchDocuments();

    const interval = setInterval(() => {
      if (!isUploading) {
        fetchDocuments();
      }
    }, 15000);

    return () => clearInterval(interval);
  }, [isOpen, fetchDocuments, isUploading, isMounted]);

  // 문서 다운로드 확인 대화상자 처리
  const handleDownloadDoc = (e: React.MouseEvent, doc: any) => {
    e.stopPropagation();

    // 💡 안전한 window.confirm 접근 (브라우저 환경 검증)
    if (typeof window === "undefined") return;
    
    // 다운로드 파일명 조합
    const parts = [
      doc.manufacturer,
      doc.model_series,
      doc.doc_type || doc.filename
    ].filter(Boolean);
    
    const fallbackName = doc.filename.endsWith(".pdf") ? doc.filename : `${doc.filename}.pdf`;
    let downloadName = parts.length > 0 ? `${parts.join("_")}` : fallbackName;
    if (parts.length > 0 && !downloadName.endsWith(".pdf")) {
      downloadName += ".pdf";
    }
    
    const confirmMessage = `📥 "${downloadName}" 문서를 다운로드하시겠습니까?\n\n💡 안내: 보안 임시 서명 링크(Signed URL)를 생성하여 클라우드 스토리지(GCS)에서 직접 다운로드됩니다.`;
    
    if (window.confirm(confirmMessage)) {
      downloadDoc(doc.document_id);
    }
  };

  // 다중 파일 업로드 처리
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    
    await processUploadFiles(files);
    
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // 드래그 앤 드롭 파일 드롭 처리
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    if (files.length === 0) return;
    
    await processUploadFiles(files);
  };

  // 파일 업로드 공통 로직
  async function processUploadFiles(files: File[]) {
    const pdfFiles = files.filter(f => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfFiles.length === 0) {
      alert("PDF 파일만 업로드할 수 있습니다.");
      return;
    }

    await uploadDocuments(pdfFiles);
  }

  // 세션 삭제 확인
  const handleDeleteSession = (sessionId: string) => {
    // 💡 안전한 window.confirm 접근
    if (typeof window === "undefined") return;

    if (window.confirm("정말로 이 대화를 삭제하시겠습니까?")) {
      deleteSession(sessionId);
      onClose?.();
    }
  };

  // 문서 삭제 확인
  const handleDeleteDoc = (doc: Document) => {
    // 💡 안전한 window.confirm 접근
    if (typeof window === "undefined") return;

    const docName = `${doc.manufacturer || "문서"} - ${doc.doc_type || doc.filename}`;
    if (window.confirm(`"${docName}" 문서를 삭제하시겠습니까?`)) {
      deleteDoc(doc.document_id);
    }
  };

  // 마운트 전에는 조건부 렌더링 방어막
  if (!isMounted) {
    return null;
  }

  return (
    <aside
      className={`fixed left-0 top-0 bottom-0 z-20 w-64 bg-background border-r border-border/50 transition-all duration-300 ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      } md:static md:translate-x-0 flex flex-col overflow-hidden`}
    >
      {/* 헤더 영역 (타이틀 + 닫기 버튼) */}
      <div className="flex-shrink-0 flex items-center justify-between h-14 px-4 border-b border-border/30">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-sm">
            <span className="text-white text-[10px] font-bold">V</span>
          </div>
          <h2 className="font-semibold text-[15px] tracking-tight">Vision RAG</h2>
        </div>
        <button
          onClick={onClose}
          className="md:hidden p-1 text-muted-foreground hover:text-foreground rounded-lg transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 스크롤 가능한 콘텐츠 영역 */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {/* 새 대화 생성 버튼 */}
        <div className="p-3 space-y-2">
          <button
            onClick={() => {
              const newSessionId = createSession("새 대화");
              setActiveSession(newSessionId);
              onClose?.();
            }}
            className="w-full flex items-center justify-center gap-2 h-9 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary font-medium text-sm transition-colors"
          >
            <PlusCircle className="w-4 h-4" />
            새 대화
          </button>
        </div>

        {/* 대화 목록 */}
        <div className="space-y-1 px-2 pb-4">
          <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            📌 대화 기록
          </div>
          {mySessions.length === 0 ? (
            <div className="px-2 py-3 text-xs text-muted-foreground/60 text-center">
              대화 기록이 없습니다.
            </div>
          ) : (
            mySessions.map((session) => (
              <div key={session.id} className="group relative">
                <button
                  onClick={() => {
                    setActiveSession(session.id);
                    onClose?.();
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all duration-200 truncate ${
                    activeSessionId === session.id
                      ? "bg-primary/15 text-primary font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                  }`}
                  title={session.title}
                >
                  <div className="flex items-center gap-2 truncate">
                    <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{session.title}</span>
                  </div>
                </button>
                <button
                  onClick={() => handleDeleteSession(session.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                  title="삭제"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* 문서 관리 섹션 */}
        <div className="border-t border-border/30 py-3 space-y-2">
          {/* 문서 업로드 */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`mx-2 p-3 rounded-lg border-2 border-dashed transition-all ${
              isDragging
                ? "border-primary/80 bg-primary/10"
                : "border-border/40 bg-accent/20 hover:border-primary/40"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="w-full flex items-center justify-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  업로드 중... ({uploadingIndex + 1}/{uploadTotal})
                </>
              ) : (
                <>
                  <UploadCloud className="w-4 h-4" />
                  PDF 업로드 (드래그 가능)
                </>
              )}
            </button>
            {isUploading && (
              <div className="mt-2 w-full h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            )}
          </div>

          {/* 분석 중인 문서 알림 */}
          {analyzingDocuments.length > 0 && (
            <div className="mx-2 p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-blue-500/80">
                <p className="font-medium">분석 중인 문서</p>
                <p className="text-blue-500/60 mt-0.5">{analyzingDocuments.length}개</p>
              </div>
            </div>
          )}
        </div>

        {/* 문서 목록 검색 */}
        {documents.length > 0 && (
          <div className="px-3 py-2 border-t border-border/30">
            <div className="flex items-center gap-2 px-2 py-1.5 bg-accent/30 rounded-lg">
              <Search className="w-3.5 h-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="문서 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value.toLowerCase())}
                className="flex-1 bg-transparent text-xs outline-none text-foreground placeholder-muted-foreground/50"
              />
            </div>
          </div>
        )}

        {/* 문서 목록 */}
        <div className="space-y-1 px-2 pb-4">
          <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            📚 관리 문서 ({documents.length})
          </div>
          {documents.length === 0 ? (
            <div className="px-2 py-3 text-xs text-muted-foreground/60 text-center">
              업로드된 문서가 없습니다.
            </div>
          ) : (
            Object.entries(
              documents.reduce(
                (acc, doc) => {
                  const mfg = doc.manufacturer || "미분류";
                  if (!acc[mfg]) acc[mfg] = {};
                  const model = doc.model_series || "기타";
                  if (!acc[mfg][model]) acc[mfg][model] = [];
                  acc[mfg][model].push(doc);
                  return acc;
                },
                {} as Record<string, Record<string, Document[]>>
              )
            )
              .map(([manufacturer, modelGroup]) =>
                Object.entries(modelGroup).map(([model, docs]) => {
                  const filteredDocs = docs.filter(
                    (doc) =>
                      !searchQuery ||
                      (doc.doc_type && doc.doc_type.toLowerCase().includes(searchQuery)) ||
                      (doc.filename && doc.filename.toLowerCase().includes(searchQuery))
                  );

                  if (filteredDocs.length === 0) return null;

                  const docKey = `${manufacturer}|${model}`;
                  const isExpanded = expandedModels[docKey];

                  return (
                    <div key={docKey} className="space-y-1">
                      <button
                        onClick={() => {
                          setExpandedModels({
                            ...expandedModels,
                            [docKey]: !isExpanded,
                          });
                        }}
                        className="w-full flex items-center gap-2 px-2 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent/50 transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
                        )}
                        <Building className="w-3 h-3 flex-shrink-0" />
                        <span className="truncate">
                          {manufacturer} - {model}
                        </span>
                      </button>

                      {isExpanded && (
                        <div className="ml-4 space-y-1">
                          {filteredDocs.map((doc) => (
                            <div key={doc.document_id} className="group relative">
                              <button
                                onClick={() => {
                                  if (editingDocId === doc.document_id) {
                                    setEditingDocId(null);
                                  } else {
                                    setEditingDocId(doc.document_id);
                                    setEditingMfg(doc.manufacturer || "");
                                    setEditingModel(doc.model_series || "");
                                    setEditingName(doc.doc_type || doc.filename);
                                  }
                                }}
                                className={`w-full text-left px-2 py-1.5 rounded-lg text-xs transition-all duration-200 truncate flex items-center gap-2 ${
                                  editingDocId === doc.document_id
                                    ? "bg-accent/60"
                                    : `${
                                        doc.status === "analyzing"
                                          ? "text-amber-500/80 bg-amber-500/10"
                                          : doc.status === "error"
                                          ? "text-red-500/80 bg-red-500/10"
                                          : "text-muted-foreground hover:text-foreground hover:bg-accent/30"
                                      }`
                                }`}
                                title={`${doc.doc_type || doc.filename} - ${doc.status}`}
                              >
                                {doc.status === "analyzing" && (
                                  <Loader2 className="w-3 h-3 flex-shrink-0 animate-spin" />
                                )}
                                {doc.status === "error" && (
                                  <AlertCircle className="w-3 h-3 flex-shrink-0" />
                                )}
                                {!doc.status && (
                                  <FileText className="w-3 h-3 flex-shrink-0" />
                                )}
                                <span className="truncate">{doc.doc_type || doc.filename}</span>
                              </button>

                              {/* 인라인 메타 편집 */}
                              {editingDocId === doc.document_id && (
                                <div className="mt-1 p-2 bg-accent/40 rounded-lg space-y-1.5 border border-border/40">
                                  <input
                                    type="text"
                                    value={editingMfg}
                                    onChange={(e) => setEditingMfg(e.target.value)}
                                    placeholder="제조사"
                                    className="w-full px-2 py-1 text-xs bg-background/60 rounded border border-border/40 outline-none focus:border-primary/60 transition-colors"
                                  />
                                  <input
                                    type="text"
                                    value={editingModel}
                                    onChange={(e) => setEditingModel(e.target.value)}
                                    placeholder="모델명"
                                    className="w-full px-2 py-1 text-xs bg-background/60 rounded border border-border/40 outline-none focus:border-primary/60 transition-colors"
                                  />
                                  <input
                                    type="text"
                                    value={editingName}
                                    onChange={(e) => setEditingName(e.target.value)}
                                    placeholder="문서명"
                                    className="w-full px-2 py-1 text-xs bg-background/60 rounded border border-border/40 outline-none focus:border-primary/60 transition-colors"
                                  />
                                  <div className="flex gap-1 justify-end">
                                    <button
                                      onClick={() => {
                                        updateDocMeta(doc.document_id, {
                                          manufacturer: editingMfg,
                                          model_series: editingModel,
                                          doc_type: editingName,
                                        });
                                        setEditingDocId(null);
                                      }}
                                      className="px-2 py-1 text-xs bg-primary/20 hover:bg-primary/30 text-primary rounded transition-colors flex items-center gap-1"
                                    >
                                      <Check className="w-3 h-3" />
                                      저장
                                    </button>
                                    <button
                                      onClick={() => setEditingDocId(null)}
                                      className="px-2 py-1 text-xs bg-muted/40 hover:bg-muted/60 text-muted-foreground rounded transition-colors"
                                    >
                                      취소
                                    </button>
                                  </div>
                                </div>
                              )}

                              {/* 문서 액션 버튼 */}
                              {editingDocId !== doc.document_id && (
                                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                  <button
                                    onClick={(e) => handleDownloadDoc(e, doc)}
                                    title="다운로드"
                                    className="p-1 text-muted-foreground hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors"
                                  >
                                    <Download className="w-3 h-3" />
                                  </button>
                                  <button
                                    onClick={() => handleDeleteDoc(doc)}
                                    title="삭제"
                                    className="p-1 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )
              .filter(Boolean)
          )}
        </div>
      </div>
    </aside>
  );
}
