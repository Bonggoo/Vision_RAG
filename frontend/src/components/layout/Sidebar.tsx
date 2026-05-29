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

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession } =
    useChatStore();
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
    const isDesktop = () => typeof window !== "undefined" && window.innerWidth >= 768;
    if (!isDesktop() && !isOpen) return;

    fetchDocuments();

    const interval = setInterval(() => {
      if (!isUploading) {
        fetchDocuments();
      }
    }, 15000);

    return () => clearInterval(interval);
  }, [isOpen, fetchDocuments, isUploading]);

  // 문서 다운로드 확인 대화상자 처리
  const handleDownloadDoc = (e: React.MouseEvent, doc: any) => {
    e.stopPropagation();
    
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
    
    const confirmMessage = `📥 "${downloadName}" 문서를 다운로드하시겠습니까?\n\n💡 안내: 보안 임시 서명 링크(Signed URL)를 생성하여 클라우드 스토리지(GCS)로부터 즉시 안전하게 초고속 다운로드합니다.`;
    
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
    const pdfFiles = files.filter(f => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    
    if (pdfFiles.length === 0) {
      alert("PDF 파일만 업로드할 수 있습니다.");
      return;
    }
    
    await processUploadFiles(pdfFiles);
  };

  // 공통 파일 업로드 프로세스
  const processUploadFiles = async (files: File[]) => {
    try {
      const results = await uploadDocuments(files);
      
      const successCount = results.filter(r => r.status === "success").length;
      const dupCount = results.filter(r => r.status === "duplicate").length;
      const errCount = results.filter(r => r.status === "error").length;
      
      let alertMsg = `🎉 업로드 완료! (성공: ${successCount}개`;
      if (dupCount > 0) alertMsg += `, 중복: ${dupCount}개`;
      if (errCount > 0) alertMsg += `, 실패: ${errCount}개`;
      alertMsg += `)`;
      
      if (errCount > 0 || dupCount > 0) {
        alertMsg += "\n\n──────────────────\n상세 내역:";
        results.forEach(r => {
          if (r.status === "duplicate") alertMsg += `\n⚠️ [중복 업로드 방지] ${r.filename}`;
          if (r.status === "error") alertMsg += `\n❌ [업로드 실패] ${r.filename}: ${r.errorMsg}`;
        });
      }
      alert(alertMsg);
      fetchDocuments();
    } catch (err: any) {
      alert(err.message || "파일 업로드 과정에서 오류가 발생했습니다.");
    }
  };

  // 분석 실패 문서 비동기 재분석 트리거
  const handleRetryAnalysis = async (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API_BASE_URL}/upload/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: doc.document_id,
          filename: doc.filename,
          file_hash: doc.file_hash || ""
        })
      });
      if (!res.ok) {
        let errorMsg = "재분석 요청 실패";
        try {
          const errData = await res.json();
          if (errData && errData.detail) errorMsg = errData.detail;
        } catch (err) {}
        throw new Error(errorMsg);
      }
      alert("🔄 AI 분석을 다시 시작했습니다!");
      fetchDocuments();
    } catch (err: any) {
      alert(`재분석 시작 실패: ${err.message}`);
    }
  };

  const handleNewChat = () => {
    const sessionId = createSession("새로운 대화");
    setActiveSession(sessionId);
    onClose?.();
  };

  const handleDeleteDoc = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    if (confirm("이 문서를 삭제하시겠습니까? 관련 데이터가 모두 영구 제거됩니다.")) {
      await deleteDoc(docId);
    }
  };

  const handleStartRename = (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    setEditingDocId(doc.document_id);
    setEditingMfg(doc.manufacturer || "");
    setEditingModel(doc.model_series || "");
    setEditingName(doc.filename);
  };

  const handleSaveMeta = async (docId: string) => {
    const trimmedName = editingName.trim();
    if (!trimmedName) {
      alert("문서 제목은 필수입니다.");
      return;
    }
    
    try {
      await updateDocMeta(docId, {
        filename: trimmedName,
        manufacturer: editingMfg.trim() || undefined,
        model_series: editingModel.trim() || undefined
      });
      setEditingDocId(null);
    } catch (err: any) {
      alert(err.message || "메타데이터 수정에 실패했습니다.");
    }
  };

  // 실시간 필터링 검색
  const filteredDocuments = documents.filter((doc) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    
    return (
      doc.filename.toLowerCase().includes(query) ||
      (doc.manufacturer || "").toLowerCase().includes(query) ||
      (doc.model_series || "").toLowerCase().includes(query)
    );
  });

  // 추천용 제조사 목록 추출
  const existingManufacturers = Array.from(
    new Set(documents.map(d => d.manufacturer).filter(Boolean))
  ) as string[];

  // 접기/펼치기 아코디언 토글
  const toggleManufacturer = (mfg: string) => {
    setExpandedManufacturers(prev => ({
      ...prev,
      [mfg]: prev[mfg] === false ? true : false // 기본 펼침(undefined -> true -> false)
    }));
  };

  const toggleModel = (model: string) => {
    setExpandedModels(prev => ({
      ...prev,
      [model]: prev[model] === false ? true : false
    }));
  };

  // 2단 트리 그룹핑 헬퍼 함수
  const getGroupedDocs = (docs: Document[]) => {
    const grouped: Record<string, Record<string, Document[]>> = {};
    docs.forEach((doc) => {
      const mfg = doc.manufacturer || "미분류";
      const model = doc.model_series || "미분류";
      if (!grouped[mfg]) grouped[mfg] = {};
      if (!grouped[mfg][model]) grouped[mfg][model] = [];
      grouped[mfg][model].push(doc);
    });
    return grouped;
  };

  const groupedDocs = getGroupedDocs(filteredDocuments);

  // 문서 렌더링 함수 (트리 뷰 or 플랫 리스트)
  const renderDocumentList = () => {
    if (filteredDocuments.length === 0) {
      return (
        <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">
          {searchQuery ? "검색 결과가 없습니다" : "업로드된 문서가 없습니다"}
        </p>
      );
    }

    // 💡 전체 문서 개수가 3개 이하이거나 검색 결과가 3개 이하일 때는 트리 구조 대신 플랫 리스트로 표시
    if (documents.length <= 3 || filteredDocuments.length <= 3) {
      return (
        <div className="space-y-1">
          {filteredDocuments.map((doc) => renderSingleDocItem(doc))}
        </div>
      );
    }

    // 트리 2단 그룹 렌더링
    return (
      <div className="space-y-2.5">
        {Object.entries(groupedDocs).map(([mfg, models]) => {
          const isMfgExpanded = expandedManufacturers[mfg] !== false;
          
          return (
            <div key={mfg} className="space-y-1">
              {/* 제조사 1단 헤더 */}
              <button
                onClick={() => toggleManufacturer(mfg)}
                className="w-full flex items-center justify-between text-xs font-semibold text-foreground/80 hover:text-foreground hover:bg-accent/30 py-1.5 px-2 rounded-lg transition-all"
              >
                <div className="flex items-center gap-1.5 truncate">
                  {mfg === "미분류" ? (
                    <Folder className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" />
                  ) : (
                    <Building className="w-3.5 h-3.5 text-primary/70 shrink-0" />
                  )}
                  <span className="truncate">{mfg}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-muted-foreground/50 font-normal">
                    ({Object.values(models).flat().length})
                  </span>
                  {isMfgExpanded ? (
                    <ChevronDown className="w-3 h-3 text-muted-foreground/60 shrink-0" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-muted-foreground/60 shrink-0" />
                  )}
                </div>
              </button>

              {/* 2단 모델 시리즈 영역 */}
              {isMfgExpanded && (
                <div className="pl-3.5 border-l border-border/40 ml-3.5 space-y-1 pt-0.5">
                  {Object.entries(models).map(([model, docs]) => {
                    const isModelExpanded = expandedModels[`${mfg}-${model}`] !== false;
                    
                    return (
                      <div key={model} className="space-y-0.5">
                        {/* 모델 2단 헤더 */}
                        <button
                          onClick={() => toggleModel(`${mfg}-${model}`)}
                          className="w-full flex items-center justify-between text-[11px] font-medium text-foreground/70 hover:text-foreground hover:bg-accent/30 py-1 px-1.5 rounded transition-all"
                        >
                          <div className="flex items-center gap-1 truncate">
                            <Cpu className="w-3 h-3 text-blue-500/60 shrink-0" />
                            <span className="truncate">{model}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-[9px] text-muted-foreground/50 font-normal">
                              ({docs.length})
                            </span>
                            {isModelExpanded ? (
                              <ChevronDown className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />
                            ) : (
                              <ChevronRight className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />
                            )}
                          </div>
                        </button>

                        {/* 문서 아이템 */}
                        {isModelExpanded && (
                          <div className="pl-2 space-y-0.5 pt-0.5">
                            {docs.map((doc) => renderSingleDocItem(doc))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // 개별 문서 아이템 렌더링 헬퍼
  const renderSingleDocItem = (doc: Document) => {
    const isEditing = editingDocId === doc.document_id;
    
    return (
      <div
        key={doc.document_id}
        className="doc-item group flex flex-col gap-1.5 px-2.5 py-2 rounded-lg hover:bg-accent/40 transition-all border border-transparent hover:border-border/20 bg-accent/5"
      >
        {isEditing ? (
          <div className="w-full space-y-2.5 p-2.5 bg-background/60 rounded-lg border border-border/30 shadow-inner" onClick={e => e.stopPropagation()}>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">제조사</label>
              <input
                type="text"
                list="manufacturers-list"
                placeholder="제조사 (예: 미쯔비시)"
                value={editingMfg}
                onChange={e => setEditingMfg(e.target.value)}
                className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">모델 시리즈</label>
              <input
                type="text"
                placeholder="모델 시리즈 (예: MR-J5)"
                value={editingModel}
                onChange={e => setEditingModel(e.target.value)}
                className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">문서 제목</label>
              <input
                type="text"
                placeholder="문서 제목"
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs"
              />
            </div>
            <div className="flex justify-end gap-1.5 pt-1">
              <button
                onClick={() => setEditingDocId(null)}
                className="px-3 py-1.5 md:px-2 md:py-0.5 text-[11px] md:text-[10px] font-medium rounded hover:bg-accent text-muted-foreground transition-colors"
              >
                취소
              </button>
              <button
                onClick={() => handleSaveMeta(doc.document_id)}
                className="px-3.5 py-1.5 md:px-2.5 md:py-0.5 text-[11px] md:text-[10px] font-medium bg-primary text-white rounded hover:bg-primary/90 flex items-center gap-1 transition-colors shadow-sm"
              >
                <Check className="w-3 h-3 md:w-2.5 md:h-2.5" /> 저장
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            {/* 썸네일 아이콘 분기 */}
            <div className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 ${
              doc.status === "analyzing"
                ? "bg-amber-500/10 text-amber-500"
                : doc.status === "error"
                ? "bg-destructive/10 text-destructive"
                : "bg-primary/10 text-primary/70"
            }`}>
              {doc.status === "analyzing" ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : doc.status === "error" ? (
                <AlertCircle className="w-3 h-3" />
              ) : (
                <FileText className="w-3 h-3" />
              )}
            </div>
            
            <div className="flex-1 min-w-0">
              <p className="text-xs md:text-[11px] font-medium text-foreground/80 group-hover:text-foreground line-clamp-3 break-all leading-tight pr-1">
                {doc.filename}
              </p>
              
              {/* 메타 배지 및 상태 배지 분기 */}
              <div className="flex flex-wrap gap-1 mt-1 text-[9px] text-muted-foreground/50">
                {doc.status === "analyzing" ? (
                  <span className="text-amber-500 font-semibold animate-pulse flex items-center gap-0.5">
                    🤖 AI 분석 중...
                  </span>
                ) : doc.status === "error" ? (
                  <span 
                    title={(doc as any).error_message || "분석 중 에러가 발생했습니다."} 
                    className="text-destructive font-semibold cursor-help"
                  >
                    ❌ 분석 실패 (마우스 오버로 사유 확인)
                  </span>
                ) : (
                  <>
                    <span>{doc.total_pages}p</span>
                    {doc.manufacturer && (
                      <span className="bg-primary/5 px-1 rounded text-primary/80 truncate max-w-[60px]">
                        {doc.manufacturer}
                      </span>
                    )}
                    {doc.model_series && (
                      <span className="bg-blue-500/5 px-1 rounded text-blue-500/80 truncate max-w-[60px]">
                        {doc.model_series}
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* 유틸 단추들 */}
            <div className="flex items-center gap-0.5 shrink-0 self-start">
              {/* 재분석 버튼 (에러 상태일 때 노출) */}
              {doc.status === "error" && (
                <button
                  onClick={(e) => handleRetryAnalysis(e, doc)}
                  title="AI 재분석 요청"
                  className="opacity-100 p-1 rounded hover:bg-amber-500/20 text-amber-500 transition-all animate-pulse"
                >
                  <RotateCw className="w-3 h-3" />
                </button>
              )}

              {/* 다운로드 버튼 (성공 시에만 노출) */}
              {doc.status !== "analyzing" && doc.status !== "error" && (
                <button
                  onClick={(e) => handleDownloadDoc(e, doc)}
                  title="다운로드"
                  className="opacity-100 md:opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"
                >
                  <Download className="w-3 h-3" />
                </button>
              )}
              
              {/* 편집 버튼 (성공 시에만 노출) */}
              {doc.status !== "analyzing" && doc.status !== "error" && (
                <button
                  onClick={(e) => handleStartRename(e, doc)}
                  title="메타 수정"
                  className="opacity-100 md:opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"
                >
                  <Pencil className="w-3 h-3" />
                </button>
              )}

              {/* 삭제 버튼 (공통 노출) */}
              <button
                onClick={(e) => handleDeleteDoc(e, doc.document_id)}
                title="삭제"
                className="opacity-100 md:opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const sidebarContent = (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex flex-col h-full relative transition-all duration-300 ${
        isDragging
          ? "border-2 border-dashed border-primary bg-primary/5 shadow-2xl scale-[0.99] rounded-xl"
          : "bg-background"
      }`}
    >
      {/* 드래그 오버 시 시각적 하이라이트 텍스트 */}
      {isDragging && (
        <div className="absolute inset-0 bg-primary/5 backdrop-blur-[1px] flex flex-col items-center justify-center pointer-events-none z-50">
          <UploadCloud className="w-12 h-12 text-primary animate-bounce mb-2" />
          <p className="text-sm font-bold text-primary">PDF 문서를 놓아 업로드하세요</p>
          <p className="text-xs text-muted-foreground/70 mt-1">다중 파일 순차 업로드 지원</p>
        </div>
      )}

      {/* 로고 + 버튼 */}
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center shadow-lg">
              <span className="text-white text-xs font-bold">V</span>
            </div>
            <span className="text-sm font-semibold tracking-tight">Vision RAG</span>
          </div>
          {onClose && (
            <button onClick={onClose} className="md:hidden p-1 rounded hover:bg-accent/50 text-muted-foreground">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <input
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileUpload}
        />
        
        {/* 다목적 업로드 버튼 */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium relative overflow-hidden transition-all ${
            isUploading
              ? "bg-primary/5 border border-primary/20 text-primary cursor-not-allowed"
              : "btn-secondary"
          }`}
        >
          {/* 업로드 순차 진행률 바 */}
          {isUploading && (
            <div 
              className="absolute left-0 top-0 bottom-0 bg-primary/10 transition-all duration-300 ease-out"
              style={{ width: `${uploadProgress}%` }}
            />
          )}
          
          <div className="flex items-center gap-2 relative z-10 w-full justify-center">
            {isUploading ? (
              <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            ) : (
              <UploadCloud className="w-4 h-4 shrink-0" />
            )}
            <span className="truncate text-xs font-semibold">
              {isUploading
                ? `업로드 중... (${uploadingIndex + 1}/${uploadTotal})`
                : "PDF 매뉴얼 업로드 (다중 선택)"}
            </span>
          </div>
        </button>

        <button
          onClick={handleNewChat}
          className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium !text-white shadow-md shadow-primary/20 hover:shadow-primary/30"
        >
          <PlusCircle className="w-4 h-4" />
          새 대화 시작
        </button>
      </div>

      <div className="h-px bg-border/50 mx-4" />

      {/* 📍 검색창 추가 */}
      <div className="px-4 pt-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
          <input
            type="text"
            placeholder="문서 검색 (이름, 제조사, 모델)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-8 py-1.5 text-[11px] rounded-lg bg-accent/20 border border-transparent focus:border-primary/30 focus:bg-accent/10 focus:outline-none transition-all placeholder:text-muted-foreground/40 text-foreground"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-accent/70 text-muted-foreground/50"
            >
              <X className="w-2.5 h-2.5" />
            </button>
          )}
        </div>
      </div>

      {/* 업로드된 문서 목록 영역 */}
      <div className="px-3 pt-3 pb-1">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 px-2 py-1 uppercase tracking-widest">
          <FileText className="w-3 h-3" />
          업로드된 문서 {documents.length > 0 && `(${documents.length})`}
        </div>
        <div className="max-h-[340px] overflow-y-auto scrollbar-thin px-1 py-1">
          {renderDocumentList()}
        </div>
      </div>

      {/* 제조사 자동완성 데이터리스트 */}
      <datalist id="manufacturers-list">
        {existingManufacturers.map(m => (
          <option key={m} value={m} />
        ))}
      </datalist>

      <div className="h-px bg-border/50 mx-4 mt-1" />

      {/* 최근 대화 */}
      <div className="flex-1 overflow-y-auto px-3 pt-3 space-y-0.5 scrollbar-thin">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 px-2 py-1 uppercase tracking-widest">
          <MessageSquare className="w-3 h-3" />
          최근 대화
        </div>

        {sessions.length === 0 && (
          <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">
            대화 기록이 없습니다
          </p>
        )}

        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm cursor-pointer transition-all ${
              activeSessionId === session.id
                ? "bg-primary/10 text-foreground font-medium border border-primary/20"
                : "hover:bg-accent/40 text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => { setActiveSession(session.id); onClose?.(); }}
          >
            <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${
              activeSessionId === session.id ? "text-primary rotate-90" : ""
            }`} />
            <span className="truncate flex-1 text-[12px]">{session.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
              className="opacity-100 md:opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>

      {/* 하단 정보 */}
      <div className="p-4 border-t border-border/30">
        <p className="text-[10px] text-muted-foreground/40 text-center">
          Vectorless Agentic Vision RAG v1.5
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* 모바일 오버레이 */}
      {isOpen && (
        <div className="sidebar-overlay fixed inset-0 z-40 md:hidden animate-fade" onClick={onClose} />
      )}

      {/* 데스크탑: 항상 표시 / 모바일: isOpen 시 표시 */}
      <aside className={`
        sidebar w-72 h-full flex-col z-50
        hidden md:flex
      `}>
        {sidebarContent}
      </aside>

      {/* 모바일 슬라이드인 */}
      <aside className={`
        sidebar fixed top-0 left-0 w-[88vw] max-w-[360px] h-full flex flex-col z-50
        md:hidden
        transition-transform duration-300 ease-out
        ${isOpen ? "translate-x-0" : "-translate-x-full"}
      `}>
        {sidebarContent}
      </aside>
    </>
  );
}
