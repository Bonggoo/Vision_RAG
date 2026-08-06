"use client";

import React from "react";
import { ChevronDown, Download, Trash2, RefreshCw } from "lucide-react";
import { Document } from "@/store/useDocumentStore";
import { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs } from "./utils";

const UNCLASSIFIED = "미분류";
/** 문서가 이 개수 이하면 그룹 트리 대신 평면 목록으로 보여준다 */
const FLAT_LIST_THRESHOLD = 3;

interface DocTreeProps {
  documents: Document[];
  filteredDocuments: Document[];
  searchQuery: string;
  fetchError: boolean;
  onRetryFetch: () => void;
  sortBy: "latest" | "name";
  expandedManufacturers: Record<string, boolean>;
  expandedModels: Record<string, boolean>;
  onToggleManufacturer: (mfg: string) => void;
  onToggleModel: (key: string) => void;
  isReclassifying: boolean;
  onReclassify: () => void;
  onBatchDownload: (docs: Document[], groupLabel: string) => void;
  onBatchDelete: (docs: Document[], groupLabel: string) => void;
  renderDocItem: (doc: Document) => React.ReactNode;
}

type GroupedDocs = Record<string, Record<string, Document[]>>;

function groupDocs(docs: Document[]): GroupedDocs {
  const grouped: GroupedDocs = {};
  for (const doc of docs) {
    if (doc.status === "analyzing") continue;
    const mfg = doc.manufacturer || UNCLASSIFIED;
    const model = doc.model_series || UNCLASSIFIED;
    grouped[mfg] ??= {};
    grouped[mfg][model] ??= [];
    grouped[mfg][model].push(doc);
  }
  return grouped;
}

/** 미분류 그룹은 항상 마지막으로 밀고, 나머지는 sortBy 기준으로 정렬 */
function compareGroups(
  labelA: string,
  docsA: Document[],
  labelB: string,
  docsB: Document[],
  sortBy: "latest" | "name"
): number {
  if (labelA === UNCLASSIFIED) return 1;
  if (labelB === UNCLASSIFIED) return -1;
  if (sortBy === "latest") return getLatestDateInDocs(docsB) - getLatestDateInDocs(docsA);
  return sortByName(labelA, labelB);
}

function sortDocs(docs: Document[], sortBy: "latest" | "name"): Document[] {
  return [...docs].sort((a, b) =>
    sortBy === "latest" ? sortByDate(a, b) : sortByName(getDisplayFilename(a), getDisplayFilename(b))
  );
}

/** 그룹 헤더 우측의 일괄 액션 버튼 묶음 */
function GroupActions({
  docs,
  label,
  onBatchDownload,
  onBatchDelete,
  showReclassify,
  isReclassifying,
  onReclassify,
}: {
  docs: Document[];
  label: string;
  onBatchDownload: (docs: Document[], label: string) => void;
  onBatchDelete: (docs: Document[], label: string) => void;
  showReclassify?: boolean;
  isReclassifying?: boolean;
  onReclassify?: () => void;
}) {
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  return (
    <span className="flex items-center shrink-0 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
      {showReclassify && onReclassify && (
        <button
          onClick={stop(onReclassify)}
          disabled={isReclassifying}
          title="AI로 다시 분류"
          aria-label="AI로 다시 분류"
          className="btn-ghost p-1.5 rounded-md"
        >
          <RefreshCw className={`w-3 h-3 ${isReclassifying ? "animate-spin" : ""}`} />
        </button>
      )}
      <button
        onClick={stop(() => onBatchDownload(docs, label))}
        title="그룹 전체 다운로드"
        aria-label="그룹 전체 다운로드"
        className="btn-ghost p-1.5 rounded-md"
      >
        <Download className="w-3 h-3" />
      </button>
      <button
        onClick={stop(() => onBatchDelete(docs, label))}
        title="그룹 전체 삭제"
        aria-label="그룹 전체 삭제"
        className="btn-ghost p-1.5 rounded-md hover:text-destructive"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </span>
  );
}

/** 제조사 > 모델 2단 아코디언 문서 트리 */
export default function DocTree({
  documents,
  filteredDocuments,
  searchQuery,
  fetchError,
  onRetryFetch,
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
}: DocTreeProps) {
  const completedFiltered = filteredDocuments.filter((d) => d.status !== "analyzing");
  const completedAll = documents.filter((d) => d.status !== "analyzing");

  if (completedFiltered.length === 0) {
    if (!searchQuery && fetchError) {
      return (
        <div className="px-3 py-6 text-center space-y-2">
          <p className="text-[12px] text-muted-foreground">문서 목록을 불러오지 못했습니다.</p>
          <button onClick={onRetryFetch} className="text-[12px] text-primary hover:underline">
            다시 시도
          </button>
        </div>
      );
    }
    return (
      <p className="px-3 py-6 text-center text-[12px] text-muted-foreground">
        {searchQuery ? "검색 결과가 없습니다." : "업로드된 문서가 없습니다."}
      </p>
    );
  }

  // 문서가 적을 때는 트리 대신 평면 목록 (불필요한 클릭 단계 제거)
  if (completedAll.length <= FLAT_LIST_THRESHOLD || completedFiltered.length <= FLAT_LIST_THRESHOLD) {
    return <div className="space-y-0.5">{sortDocs(completedFiltered, sortBy).map(renderDocItem)}</div>;
  }

  const grouped = groupDocs(filteredDocuments);
  const manufacturers = Object.entries(grouped).sort(([mfgA, modelsA], [mfgB, modelsB]) =>
    compareGroups(mfgA, Object.values(modelsA).flat(), mfgB, Object.values(modelsB).flat(), sortBy)
  );

  return (
    <div className="space-y-1">
      {manufacturers.map(([mfg, models]) => {
        const mfgDocs = Object.values(models).flat();
        const isMfgOpen = !!expandedManufacturers[mfg];

        return (
          <div key={mfg}>
            <div className="group flex items-center gap-0.5 pr-1">
              <button
                onClick={() => onToggleManufacturer(mfg)}
                aria-expanded={isMfgOpen}
                className="nav-item flex-1 min-w-0 flex items-center gap-1.5 py-1.5 px-2 text-[12.5px] font-medium"
              >
                <ChevronDown
                  className={`w-3 h-3 shrink-0 transition-transform ${isMfgOpen ? "" : "-rotate-90"}`}
                />
                <span className="truncate flex-1 text-left">{mfg}</span>
                <span className="text-[11px] text-muted-foreground/60 shrink-0">{mfgDocs.length}</span>
              </button>
              <GroupActions
                docs={mfgDocs}
                label={mfg}
                onBatchDownload={onBatchDownload}
                onBatchDelete={onBatchDelete}
                showReclassify={mfg === UNCLASSIFIED}
                isReclassifying={isReclassifying}
                onReclassify={onReclassify}
              />
            </div>

            {isMfgOpen && (
              <div className="ml-3 pl-2 border-l border-border space-y-0.5 py-0.5">
                {Object.entries(models)
                  .sort(([modelA, docsA], [modelB, docsB]) =>
                    compareGroups(modelA, docsA, modelB, docsB, sortBy)
                  )
                  .map(([model, docs]) => {
                    const modelKey = `${mfg}-${model}`;
                    const isModelOpen = !!expandedModels[modelKey];
                    return (
                      <div key={model}>
                        <div className="group flex items-center gap-0.5 pr-1">
                          <button
                            onClick={() => onToggleModel(modelKey)}
                            aria-expanded={isModelOpen}
                            className="nav-item flex-1 min-w-0 flex items-center gap-1.5 py-1 px-1.5 text-[12px]"
                          >
                            <ChevronDown
                              className={`w-3 h-3 shrink-0 transition-transform ${
                                isModelOpen ? "" : "-rotate-90"
                              }`}
                            />
                            <span className="truncate flex-1 text-left">{model}</span>
                            <span className="text-[11px] text-muted-foreground/60 shrink-0">
                              {docs.length}
                            </span>
                          </button>
                          <GroupActions
                            docs={docs}
                            label={`${mfg} > ${model}`}
                            onBatchDownload={onBatchDownload}
                            onBatchDelete={onBatchDelete}
                          />
                        </div>
                        {isModelOpen && (
                          <div className="pl-1.5 space-y-0.5 py-0.5">
                            {sortDocs(docs, sortBy).map(renderDocItem)}
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
