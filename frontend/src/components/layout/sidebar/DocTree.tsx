"use client";

import React from "react";
import { ChevronRight, ChevronDown, Download, Building, Cpu, Folder, Trash2, RefreshCw } from "lucide-react";
import { Document } from "@/store/useDocumentStore";
import { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs } from "./utils";

/**
 * 제조사 > 모델 2단 아코디언 문서 트리 (M5 분해) — 기존 Sidebar.renderDocumentList 를 그대로 추출.
 * 그룹핑/정렬 로직(sortBy 분기, 미분류 후순위 처리)을 모두 보존한다.
 * 개별 문서 항목 렌더링은 renderDocItem 콜백(렌더 prop)으로 위임한다.
 */
export default function DocTree({
  documents,
  filteredDocuments,
  searchQuery,
  sortBy,
  expandedManufacturers,
  expandedModels,
  onToggleManufacturer,
  onToggleModel,
  isReclassifying,
  onReclassify,
  onBatchDownload,
  onBatchDelete,
  renderDocItem,
}: {
  documents: Document[];
  filteredDocuments: Document[];
  searchQuery: string;
  sortBy: "latest" | "name";
  expandedManufacturers: Record<string, boolean>;
  expandedModels: Record<string, boolean>;
  onToggleManufacturer: (mfg: string) => void;
  onToggleModel: (model: string) => void;
  isReclassifying: boolean;
  onReclassify: (e: React.MouseEvent) => void;
  onBatchDownload: (e: React.MouseEvent, docs: Document[], groupLabel: string) => void;
  onBatchDelete: (e: React.MouseEvent, docs: Document[], groupLabel: string) => void;
  renderDocItem: (doc: Document) => React.ReactNode;
}) {
  const getGroupedDocs = (docs: Document[]) => {
    const grouped: Record<string, Record<string, Document[]>> = {};
    docs.forEach((doc) => {
      if (doc.status === "analyzing") return;
      const mfg = doc.manufacturer || "미분류"; const model = doc.model_series || "미분류";
      if (!grouped[mfg]) grouped[mfg] = {}; if (!grouped[mfg][model]) grouped[mfg][model] = [];
      grouped[mfg][model].push(doc);
    });
    return grouped;
  };

  const groupedDocs = getGroupedDocs(filteredDocuments);

  const completedFilteredDocs = filteredDocuments.filter(d => d.status !== "analyzing");
  const completedDocs = documents.filter(d => d.status !== "analyzing");

  if (completedFilteredDocs.length === 0) {
    return <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">{searchQuery ? "검색 결과가 없습니다" : "업로드된 문서가 없습니다"}</p>;
  }

  if (completedDocs.length <= 3 || completedFilteredDocs.length <= 3) {
    const sortedFlatDocs = [...completedFilteredDocs].sort((a, b) => sortBy === "latest" ? sortByDate(a, b) : sortByName(getDisplayFilename(a), getDisplayFilename(b)));
    return <div className="space-y-1">{sortedFlatDocs.map((doc) => renderDocItem(doc))}</div>;
  }

  const sortedManufacturers = Object.entries(groupedDocs).sort(([mfgA, modelsA], [mfgB, modelsB]) => {
    if (mfgA === "미분류") return 1; if (mfgB === "미분류") return -1;
    if (sortBy === "latest") return getLatestDateInDocs(Object.values(modelsB).flat()) - getLatestDateInDocs(Object.values(modelsA).flat());
    return sortByName(mfgA, mfgB);
  });

  return (
    <div className="space-y-2.5">
      {sortedManufacturers.map(([mfg, models]) => {
        const isMfgExpanded = !!expandedManufacturers[mfg];
        return (
          <div key={mfg} className="space-y-1">
            <div className="group/mfg flex items-center gap-0.5">
              <button onClick={() => onToggleManufacturer(mfg)} className="flex-1 min-w-0 flex items-center justify-between text-xs font-semibold text-foreground/80 hover:text-foreground hover:bg-accent/30 py-1.5 px-2 rounded-xl transition-all">
                <div className="flex items-center gap-1.5 truncate">
                  {mfg === "미분류" ? <Folder className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" /> : <Building className="w-3.5 h-3.5 text-primary/70 shrink-0" />}
                  <span className="truncate">{mfg}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-muted-foreground/50 font-normal">({Object.values(models).flat().length})</span>
                  {isMfgExpanded ? <ChevronDown className="w-3 h-3 text-muted-foreground/60 shrink-0" /> : <ChevronRight className="w-3 h-3 text-muted-foreground/60 shrink-0" />}
                </div>
              </button>
              <div className="flex items-center gap-0.5 opacity-0 group-hover/mfg:opacity-100 transition-opacity shrink-0">
                {mfg === "미분류" && <button onClick={onReclassify} disabled={isReclassifying} className="p-1 rounded-full hover:bg-primary/20 text-muted-foreground/40 hover:text-primary transition-all"><RefreshCw className={`w-3 h-3 ${isReclassifying ? "animate-spin" : ""}`} /></button>}
                <button onClick={(e) => onBatchDownload(e, Object.values(models).flat(), mfg)} className="p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-3 h-3" /></button>
                <button onClick={(e) => onBatchDelete(e, Object.values(models).flat(), mfg)} className="p-1 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-3 h-3" /></button>
              </div>
            </div>
            {isMfgExpanded && (
              <div className="pl-3.5 border-l border-border/40 ml-3.5 space-y-1 pt-0.5">
                {Object.entries(models).sort(([modelA, docsA], [modelB, docsB]) => {
                  if (modelA === "미분류") return 1; if (modelB === "미분류") return -1;
                  if (sortBy === "latest") return getLatestDateInDocs(docsB) - getLatestDateInDocs(docsA);
                  return sortByName(modelA, modelB);
                }).map(([model, docs]) => {
                  const isModelExpanded = !!expandedModels[`${mfg}-${model}`];
                  return (
                    <div key={model} className="space-y-0.5">
                      <div className="group/model flex items-center gap-0.5">
                        <button onClick={() => onToggleModel(`${mfg}-${model}`)} className="flex-1 min-w-0 flex items-center justify-between text-[11px] font-medium text-foreground/70 hover:text-foreground hover:bg-accent/30 py-1 px-1.5 rounded-xl transition-all">
                          <div className="flex items-center gap-1 truncate"><Cpu className="w-3 h-3 text-blue-500/60 shrink-0" /><span className="truncate">{model}</span></div>
                          <div className="flex items-center gap-1"><span className="text-[9px] text-muted-foreground/50 font-normal">({docs.length})</span>{isModelExpanded ? <ChevronDown className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" /> : <ChevronRight className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />}</div>
                        </button>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover/model:opacity-100 transition-opacity shrink-0">
                          <button onClick={(e) => onBatchDownload(e, docs, `${mfg} > ${model}`)} className="p-0.5 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-2.5 h-2.5" /></button>
                          <button onClick={(e) => onBatchDelete(e, docs, `${mfg} > ${model}`)} className="p-0.5 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-2.5 h-2.5" /></button>
                        </div>
                      </div>
                      {isModelExpanded && (
                        <div className="pl-2 space-y-0.5 pt-0.5">
                          {[...docs].sort((a, b) => sortBy === "latest" ? sortByDate(a, b) : sortByName(getDisplayFilename(a), getDisplayFilename(b))).map((doc) => renderDocItem(doc))}
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
}
