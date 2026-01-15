import React from 'react';
import { BookOpen, ExternalLink, FileText } from 'lucide-react';

export function ReferenceSidebar({ sources }) {
  return (
    <div className="hidden h-screen w-80 flex-col border-r border-gray-200 bg-gray-50 md:flex">
      <div className="flex h-14 items-center border-b border-gray-200 px-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
          <BookOpen size={16} /> 资料库 ({sources.length})
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {sources.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-gray-400">
            <FileText size={48} className="mb-4 opacity-20" />
            <p className="text-sm">暂无引用文档</p>
            <p className="text-xs mt-1">开始研究后，相关资料将出现在这里</p>
          </div>
        ) : (
          sources.map((src, idx) => (
            <div 
              key={idx}
              className="group relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-gray-100 text-[10px] font-bold text-gray-500">
                  {idx + 1}
                </div>
                <a 
                  href={src.url || '#'} 
                  target="_blank" 
                  rel="noreferrer"
                  className="flex-1 text-sm font-medium text-blue-600 line-clamp-2 hover:underline"
                >
                  {src.title || "无标题文档"}
                </a>
              </div>
              <p className="mt-2 text-xs text-gray-500 line-clamp-3 leading-relaxed">
                {src.snippet || "暂无摘要..."}
              </p>
              
              {src.url && (
                <div className="absolute right-2 top-2 opacity-0 transition-opacity group-hover:opacity-100">
                  <ExternalLink size={12} className="text-gray-400" />
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
