import React, { useState, useRef, useEffect } from 'react';
import { BookOpen, ExternalLink, FileText, Terminal, Activity, ChevronDown, ChevronUp, PlusCircle, Zap } from 'lucide-react';

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
    <div className="hidden h-full w-80 flex-col border-l border-cyan-500/20 bg-gradient-to-b from-[#1a1a1a] to-[#0f0f0f] md:flex shrink-0">
      {/* Header / Tabs */}
      <div className="flex h-14 items-center border-b border-cyan-500/20 bg-[#1a1a1a]/50 shrink-0">
        <button
            onClick={() => setActiveTab('sources')}
            className={`flex-1 flex items-center justify-center gap-2 h-full text-sm font-medium transition-all relative ${
                activeTab === 'sources' ? 'text-cyan-300 bg-cyan-500/10' : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
        >
            <BookOpen size={16} />
            <span className="hidden sm:inline">资料库</span>
            <span className="inline-block sm:hidden">({sources.length})</span>
            <span className="hidden sm:inline text-xs text-cyan-400/60">({sources.length})</span>
            {activeTab === 'sources' && (
                <div className="absolute bottom-0 left-0 w-full h-1 bg-gradient-to-r from-cyan-500 to-blue-500 rounded-t" />
            )}
        </button>
        <div className="w-px h-6 bg-cyan-500/20" />
        <button
            onClick={() => setActiveTab('logs')}
            className={`flex-1 flex items-center justify-center gap-2 h-full text-sm font-medium transition-all relative ${
                activeTab === 'logs' ? 'text-purple-300 bg-purple-500/10' : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
        >
            <Zap size={16} />
            <span className="hidden sm:inline">日志</span>
             {activeTab === 'logs' && (
                <div className="absolute bottom-0 left-0 w-full h-1 bg-gradient-to-r from-purple-500 to-pink-500 rounded-t" />
            )}
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto bg-[#0f0f0f]/40 custom-scrollbar">
        
        {/* Sources Tab */}
        {activeTab === 'sources' && (
            <div className="p-4 space-y-4">
                {sources.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                    <div className="mb-4 p-3 rounded-full bg-cyan-500/10 border border-cyan-500/20">
                        <FileText size={32} className="opacity-40 text-cyan-400" />
                    </div>
                    <p className="text-sm font-medium">暂无引用文档</p>
                    <p className="text-xs mt-2 text-gray-600">开始研究后，相关资料将出现在这里</p>
                </div>
                ) : (
                // ✅ 新增：分组逻辑
                <>
                    {(() => {
                        // 1. 按 _round 分组
                        const grouped = {};
                        sources.forEach((src, idx) => {
                            const round = src._round || 'unknown';
                            const question = src._question || '未知问题';
                            const key = `round_${round}`;
                            
                            if (!grouped[key]) {
                                grouped[key] = {
                                    round: round,
                                    question: question,
                                    sources: []
                                };
                            }
                            grouped[key].sources.push(src);
                        });
                        
                        // 2. 按轮次顺序展示
                        return Object.values(grouped)
                            .sort((a, b) => parseInt(a.round) - parseInt(b.round))
                            .map((group, groupIdx) => {
                                // 3. 交替颜色：蓝色、青色、蓝色...
                                const colors = [
                                    'border-blue-500/30 bg-blue-500/5 bg-opacity-40',
                                    'border-cyan-500/30 bg-cyan-500/5 bg-opacity-40',
                                ];
                                const colorClass = colors[groupIdx % 2];
                                const bgGradient = groupIdx % 2 === 0 
                                    ? 'bg-gradient-to-r from-blue-500/10 to-transparent'
                                    : 'bg-gradient-to-r from-cyan-500/10 to-transparent';
                                
                                return (
                                    <div key={`group_${group.round}`} className={`rounded-lg border-l-4 pl-3 space-y-2.5 py-3 ${colorClass}`}>
                                        {/* 轮次标题 */}
                                        <div className={`${bgGradient} -mx-3 px-3 py-2 rounded-t-lg`}>
                                            <div className={`flex items-center gap-2 text-xs font-bold uppercase tracking-wide ${
                                                groupIdx % 2 === 0 ? 'text-blue-400' : 'text-cyan-400'
                                            }`}>
                                                <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                                                    groupIdx % 2 === 0 
                                                        ? 'bg-blue-500/40 text-blue-200' 
                                                        : 'bg-cyan-500/40 text-cyan-200'
                                                }`}>
                                                    {group.round}
                                                </span>
                                                <span>第 {group.round} 轮搜索</span>
                                            </div>
                                            <div className="mt-1.5 text-xs text-gray-300 font-medium truncate ml-7">
                                                📌 "{group.question.substring(0, 40)}{group.question.length > 40 ? '...' : ''}"
                                            </div>
                                        </div>
                                        
                                        {/* 该轮的所有资源 */}
                                        <div className="space-y-1.5 mt-2">
                                            {group.sources.map((src) => (
                                                <SourceCard 
                                                    key={`${group.round}_${src._sourceIndex}`} 
                                                    src={src} 
                                                    round={group.round}
                                                    isAlternate={groupIdx % 2 === 1}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                );
                            });
                    })()}
                </>
                )}
            </div>
        )}

        {/* Logs Tab */}
        {activeTab === 'logs' && (
            <div className="p-0 font-mono text-xs">
                {logs.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                        <div className="mb-4 p-3 rounded-full bg-purple-500/10 border border-purple-500/20">
                            <Terminal size={32} className="opacity-40 text-purple-400" />
                        </div>
                        <p className="text-sm font-medium">系统准备就绪</p>
                        <p className="text-xs mt-2 text-gray-600">等待任务指令...</p>
                    </div>
                ) : (
                    <div className="divide-y divide-white/5 bg-[#0f0f0f]">
                        {logs.map((log, i) => (
                            <div key={i} className="px-4 py-2.5 hover:bg-white/5 flex gap-2 transition-colors group">
                                <span className="text-gray-600 select-none text-[9px] w-5 text-right shrink-0 pt-0.5 font-mono group-hover:text-purple-500">
                                    {i + 1}
                                </span>
                                <div className="flex-1 break-words text-gray-400 leading-tight">
                                    {log}
                                </div>
                            </div>
                        ))}
                        <div ref={logsEndRef} className="h-2" />
                    </div>
                )}
            </div>
        )}
      </div>

      {/* Footer / Actions */}
      {onClear && (
        <div className="border-t border-cyan-500/20 p-3 bg-[#1a1a1a]/50">
            <button 
              onClick={onClear}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-4 py-2.5 text-sm font-medium text-cyan-300 transition-all hover:bg-cyan-500/20 hover:border-cyan-500/50 hover:text-cyan-200 hover:shadow-lg hover:shadow-cyan-900/20"
            >
               <PlusCircle size={16} />
               <span>新建研究</span>
            </button>
        </div>
      )}
    </div>
  );
}

function SourceCard({ src, round, isAlternate }) {
    const [expanded, setExpanded] = useState(false);
    
    // ✅ 样式根据轮次颜色变更
    const borderColor = isAlternate ? 'border-cyan-500/30' : 'border-blue-500/30';
    const bgColor = isAlternate ? 'bg-cyan-500/8 hover:bg-cyan-500/15' : 'bg-blue-500/8 hover:bg-blue-500/15';
    const expansionBorder = isAlternate ? 'border-cyan-500/50 bg-cyan-500/5 shadow-cyan-900/20' : 'border-blue-500/50 bg-blue-500/5 shadow-blue-900/20';
    const linkColor = isAlternate ? 'text-cyan-300 hover:text-cyan-200' : 'text-blue-300 hover:text-blue-200';

    return (
        <div 
        className={`group relative rounded-lg border transition-all ${
            expanded 
            ? `${expansionBorder} shadow-lg` 
            : `${borderColor} ${bgColor} shadow-sm hover:shadow-md`
        }`}
        >
        <div className="flex items-start justify-between gap-2 p-3">
            <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold border ${
                isAlternate
                    ? 'bg-gradient-to-br from-cyan-500/30 to-blue-500/30 text-cyan-300 border-cyan-500/40'
                    : 'bg-gradient-to-br from-blue-500/30 to-cyan-500/30 text-blue-300 border-blue-500/40'
            }`}>
            {src._sourceIndex}
            </div>
            <a 
            href={src.url || '#'} 
            target="_blank" 
            rel="noreferrer"
            className={`flex-1 text-xs font-semibold break-all transition-colors line-clamp-2 ${linkColor}`}
            title={src.title}
            >
            {src.title || "无标题文档"}
            </a>
            {/* Expand Toggle */}
            <button 
                onClick={() => setExpanded(!expanded)}
                className="text-gray-600 hover:text-cyan-400 p-1 transition-colors"
            >
                {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
        </div>
        
        {/* URL Preview */}
        <div className="px-3 pb-2 text-[10px] text-gray-600 truncate font-mono group-hover:text-gray-500 break-all whitespace-normal leading-tight">
            {new URL(src.url || 'http://example.com').hostname}
            <div className='text-[8px] text-gray-700 mt-0.5 break-all'>
                {src.url?.replace(/^https?:\/\//, '')?.substring(0, 60)}...
            </div>
        </div>

        {/* Snippet */}
        <div className={`text-xs text-gray-400 leading-relaxed bg-white/2 rounded-b border-t border-cyan-500/10 p-3 max-w-full${
            expanded ? '' : 'line-clamp-2'
        } break-words whitespace-normal`}>
            {src.snippet || "暂无摘要"}
        </div>
        
        {src.url && (
            <a 
              href={src.url} 
              target="_blank" 
              rel="noreferrer"
              className="absolute right-3 top-3 opacity-0 transition-opacity group-hover:opacity-100 text-cyan-400 hover:text-cyan-300"
            >
              <ExternalLink size={14} />
            </a>
        )}
      </div>
    );
}
