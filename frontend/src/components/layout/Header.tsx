import React from 'react';
import { Menu, FileUp } from 'lucide-react';

export default function Header() {
  return (
    <header className="h-14 border-b border-border bg-background flex items-center justify-between px-4 sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <button className="md:hidden p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors">
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="font-semibold text-lg tracking-tight">Vision RAG</h1>
      </div>
      
      <div className="flex items-center">
        <button className="flex items-center gap-2 text-sm font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80 py-1.5 px-3 rounded-md transition-colors">
          <FileUp className="w-4 h-4" />
          <span className="hidden sm:inline">문서 관리</span>
        </button>
      </div>
    </header>
  );
}
