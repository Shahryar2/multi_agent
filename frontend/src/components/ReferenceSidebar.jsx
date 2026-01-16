import React, { useState, useRef, useEffect } from 'react';
import { BookOpen, ExternalLink, FileText, Terminal, Activity, ChevronDown, ChevronUp, PlusCircle } from 'lucide-react';

export function ReferenceSidebar({ sources, logs = [], onClear }) {
  const [activeTab, setActiveTab] = useState('sources'); // 'sources' | 'logs'
  const logsEndRef = useRef(null);

  // Auto-scroll logs
  useEffect(() => {
    if (activeTab === 'logs' && logsEndRef.current) {
        logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, activeTab]);

  return (
    <div className="hidden h-full w-80 flex-col border-l border-white/10 bg-[#161616] md:flex shrink-0">
      {/* Header / Tabs */}
      <div className="flex h-14 items-center border-b border-white/10 bg-[#161616] shrink-0">
        <button
            onClick={() => setActiveTab('sources')}
            className={`flex-1 flex items-center justify-center gap-2 h-full text-sm font-medium transition-colors relative ${
                activeTab === 'sources' ? 'text-blue-400 bg-white/5' : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
        >
            <BookOpen size={16} />
            <span>资料库 ({sources.length})</span>
            {activeTab === 'sources' && (
                <div className="absolute bottom-0 left-0 w-full h-0.5 bg-blue-500" />
            )}
        </button>
        <div className="w-px h-6 bg-white/10" />
        <button
            onClick={() => setActiveTab('logs')}
            className={`flex-1 flex items-center justify-center gap-2 h-full text-sm font-medium transition-colors relative ${
                activeTab === 'logs' ? 'text-amber-400 bg-white/5' : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
        >
            <Activity size={16} />
            <span>执行日志</span>
             {activeTab === 'logs' && (
                <div className="absolute bottom-0 left-0 w-full h-0.5 bg-amber-500" />
            )}
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto bg-[#161616] custom-scrollbar">
        
        {/* Sources Tab */}
        {activeTab === 'sources' && (
            <div className="p-4 space-y-3">
                {sources.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                    <FileText size={48} className="mb-4 opacity-20" />
                    <p className="text-sm">暂无引用文档</p>
                    <p className="text-xs mt-1 text-gray-600">开始研究后，相关资料将出现在这里</p>
                </div>
                ) : (
                sources.map((src, idx) => (
                    <SourceCard key={idx} src={src} idx={idx} />
                ))
                )}
            </div>
        )}

        {/* Logs Tab */}
        {activeTab === 'logs' && (
            <div className="p-0 font-mono text-xs">
                {logs.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                        <Terminal size={48} className="mb-4 opacity-20" />
                        <p className="text-sm">系统准备就绪</p>
                        <p className="text-xs mt-1 text-gray-600">等待任务指令...</p>
                    </div>
                ) : (
                    <div className="divide-y divide-white/5 bg-[#161616]">
                        {logs.map((log, i) => (
                            <div key={i} className="px-4 py-3 hover:bg-white/5 flex gap-2 sm:gap-3 transition-colors">
                                <span className="text-gray-600 select-none text-[10px] w-6 text-right shrink-0 pt-0.5">
                                    {i + 1}
                                </span>
                                <div className="flex-1 break-words text-gray-400">
                                    {log}
                                </div>
                            </div>
                        ))}
                        <div ref={logsEndRef} className="h-4" />
                    </div>
                )}
            </div>
        )}
      </div>

      {/* Footer / Actions */}
      {onClear && (
        <div className="border-t border-white/10 p-3 bg-[#161616]">
            <button 
              onClick={onClear}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-gray-400 transition-colors hover:bg-white/10 hover:text-white hover:border-white/20"
            >
               <PlusCircle size={16} />
               <span>开启新研究</span>
            </button>
        </div>
      )}
    </div>
  );
}

function SourceCard({ src, idx }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div 
        className={`group relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm transition-all hover:shadow-md ${expanded ? 'ring-1 ring-blue-100' : ''}`}
        >
        <div className="flex items-start justify-between gap-2">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-gray-100 text-[10px] font-bold text-gray-500">
            {idx + 1}
            </div>
            <a 
            href={src.url || '#'} 
            target="_blank" 
            rel="noreferrer"
            className="flex-1 text-sm font-medium text-blue-600 break-all hover:underline"
            title={src.title}
            >
            {src.title || "无标题文档"}
            </a>
            {/* Expand Toggle */}
            <button 
                onClick={() => setExpanded(!expanded)}
                className="text-gray-400 hover:text-gray-600 p-1"
            >
                {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
        </div>
        
        {/* URL Preview if title is weird */}
        <div className="mt-1 mb-2 text-[10px] text-gray-400 truncate px-7">
            {src.url}
        </div>

        <div className={`text-xs text-gray-500 leading-relaxed bg-gray-50 rounded p-2 ${expanded ? '' : 'line-clamp-3'}`}>
            {src.snippet || "暂无摘要..."}
        </div>
        
        {src.url && (
            <div className="absolute right-8 top-3 opacity-0 transition-opacity group-hover:opacity-100">
            <a href={src.url} target="_blank" rel="noreferrer">
                <ExternalLink size={12} className="text-gray-400 hover:text-blue-500" />
            </a>
            </div>
        )}
        </div>
    );
}
