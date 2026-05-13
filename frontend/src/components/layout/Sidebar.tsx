import React, { useRef } from 'react';
import { PlusCircle, MessageSquare, UploadCloud, Loader2 } from 'lucide-react';
import { useChatStore } from '@/store/useChatStore';
import { useDocumentStore } from '@/store/useDocumentStore';

export default function Sidebar() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { sessions, activeSessionId, setActiveSession, createSession } = useChatStore();
  const { uploadDocument, isUploading } = useDocumentStore();

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const doc = await uploadDocument(file);
      // 업로드 완료 후 새 대화 생성
      const sessionId = createSession(doc.document_id, `${file.name.slice(0, 15)}... 대화`);
      setActiveSession(sessionId);
    } catch (err) {
      alert('파일 업로드에 실패했습니다.');
    }
    
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleNewChat = () => {
    const sessionId = createSession(null, '새로운 대화');
    setActiveSession(sessionId);
  };

  return (
    <aside className="w-64 h-full bg-card border-r border-border hidden md:flex flex-col">
      <div className="p-4 border-b border-border space-y-3">
        <input 
          type="file" 
          accept="application/pdf"
          className="hidden" 
          ref={fileInputRef}
          onChange={handleFileUpload}
        />
        <button 
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="w-full flex items-center justify-center gap-2 bg-secondary text-secondary-foreground hover:bg-secondary/80 py-2 px-4 rounded-md transition-colors disabled:opacity-50"
        >
          {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
          <span className="font-medium text-sm">{isUploading ? '업로드 중...' : 'PDF 매뉴얼 업로드'}</span>
        </button>

        <button 
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 py-2 px-4 rounded-md transition-colors"
        >
          <PlusCircle className="w-4 h-4" />
          <span className="font-medium text-sm">새 대화 시작</span>
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        <div className="text-xs font-semibold text-muted-foreground px-2 py-2 uppercase tracking-wider">
          최근 대화
        </div>
        
        {sessions.map((session) => (
          <button 
            key={session.id}
            onClick={() => setActiveSession(session.id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 text-left rounded-md text-sm group transition-colors ${
              activeSessionId === session.id 
                ? 'bg-accent text-accent-foreground font-medium' 
                : 'hover:bg-accent/50 text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare className="w-4 h-4 shrink-0" />
            <span className="truncate flex-1">{session.title}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
