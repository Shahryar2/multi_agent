import React, { useState, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Send, LogIn, UserCircle, Bot, Activity, Clock, Search, ChevronRight, Loader2, PanelRightClose, PanelRightOpen, Brain, Sparkles, Image, ExternalLink } from 'lucide-react';
import { ReferenceSidebar } from './components/ReferenceSidebar';
import { ApprovalModal } from './components/ApprovalModal';
import { LoginModal } from './components/LoginModal';
import { getTaskState, startTask, stopTask, approvePlan, syncHistory, getHistory, API_BASE } from './lib/api';

function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('di_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [showLogin, setShowLogin] = useState(false);
  
  // Load initial state
  const [messages, setMessages] = useState(() => {
    const saved = localStorage.getItem('di_messages');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sources, setSources] = useState([]);
  const [logs, setLogs] = useState([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Approval State
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(() => localStorage.getItem('di_thread_id'));  
  
  // Persist messages
  useEffect(() => {
    localStorage.setItem('di_messages', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    async function restoreSession() {
      if (!activeThreadId) return;

      try {
        console.log("正在恢复会话状态:", activeThreadId);
        const stateData = await getTaskState(activeThreadId);
        
        if (stateData && stateData.values) {
          const { documents, citations } = stateData.values;
          
          // 1. 恢复资料库 (Reference Library)
          // 后端 documents 可能包含很多字段，这里做一下去重和格式化
          if (documents && Array.isArray(documents)) {
            const uniqueDocs = [];
            const seenUrls = new Set();
            
            documents.forEach(doc => {
              // 兼容不同的数据结构 (state.py 里可能是 dict 也可能是 object)
              const url = doc.url || doc.metadata?.source;
              const title = doc.title || doc.metadata?.title || "未知文档";
              
              if (url && !seenUrls.has(url)) {
                seenUrls.add(url);
                uniqueDocs.push({
                  title: title,
                  url: url,
                  type: 'website' // 或根据 doc.type 判断
                });
              }
            });
            
            if (uniqueDocs.length > 0) {
              setSources(uniqueDocs);
              console.log("已恢复资料库:", uniqueDocs.length, "条");
            }
          }
          
          // 2. 如果需要，也可以恢复待批准的计划 (Fix: 刷新后批准弹窗消失的问题)
          if (stateData.values.plan && stateData.values.plan.length > 0) {
             // 简单的逻辑：如果最新状态还有 pending 的计划，可能需要恢复弹窗
             // 但通常比较复杂，这里先只解决资料库
          }
        }
      } catch (err) {
        console.warn("无法恢复历史状态 (可能是新任务):", err);
      }
    }

    restoreSession();
  }, [activeThreadId]); // 依赖项：当 activeThreadId 变化时执行  
    

  useEffect(() => {
    if(activeThreadId) localStorage.setItem('di_thread_id', activeThreadId);
    // Sync to server if user logged in
    if (user && activeThreadId && messages.length > 0) {
        const timeout = setTimeout(() => {
            syncHistory(user.id, activeThreadId, messages).catch(console.error);
        }, 3000);
        return () => clearTimeout(timeout);
    }
  }, [activeThreadId, messages, user]);

  const reportContainerRef = useRef(null);

  // Auto-scroll
  useEffect(() => { 
      if (reportContainerRef.current) {
         reportContainerRef.current.scrollTop = reportContainerRef.current.scrollHeight;
      }
  }, [messages]);

  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString([], { hour12: false });
    setLogs(prev => [...prev, `[${time}] ${msg}`]);
  };

  // Clear Chat Function
  const clearChat = () => {
    setMessages([]);
    setSources([]);
    setLogs([]);
    setPendingPlan([]);
    setActiveThreadId(null);
    localStorage.removeItem('di_messages');
    localStorage.removeItem('di_thread_id');
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    // Clear previous if starting new
    if (messages.length > 0 && !isLoading) {
       clearChat(); 
       // small delay to allow state clear
       await new Promise(r => setTimeout(r, 0));
    }

    const query = input;
    setInput('');
    // Initial user message
    setMessages([
        { role: 'user', content: query },
        { role: 'assistant', content: ''}
    ]);
    setIsLoading(true);
    addLog(`Starting task: ${query.substring(0, 20)}...`);

    try {
      const { thread_id } = await startTask(query, user?.id);
      setActiveThreadId(thread_id);
      connectStream(thread_id);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ Error: ${err.message}` }]);
      setIsLoading(false);
    }
  };

  const connectStream = (threadId) => {
    const eventSource = new EventSource(`${API_BASE}/research/${threadId}/stream`);
    // Store eventSource in a ref if I wanted to stop it, or just use a state/callback.
    // For now, let's keep it simple. But to implement stop, we need a ref.
    window.currentEventSource = eventSource;
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('📨 SSE Event received:', data);
        
        // Interrupt
        if (data.type === 'interrupt') {
          // --- 专门针对 interrupt 事件的详细日志 ---
          console.log('✅ INTERRUPT event detected!');
          console.log('Plan data received:', data.plan);
          console.log('Is plan an array?', Array.isArray(data.plan));
          console.log('Plan length:', data.plan ? data.plan.length : 'undefined');
          
          eventSource.close();
          setPendingPlan(data.plan || []);
          setIsApprovalOpen(true);
          addLog("Paused for plan approval.");
          return;
        }

        // Logs
        if (data.node) {
          addLog(`Node Executed: ${data.node}`);
        }

        // Search Results
        if (data.search_results) {
             setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant') {
                    return [...prev.slice(0, -1), { ...last, searchResults: data.search_results }];
                }
                // If it arrives before any content? Should ideally exist or we create one.
                return [...prev, { role: 'assistant', searchResults: data.search_results }];
             });
        }

        // Thought Process
        if (data.thought) {
             setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant') {
                    return [...prev.slice(0, -1), { ...last, thought: data.thought }];
                }
                return prev;
             });
        }

        // Streaming Content (Delta)
        if (data.delta) {
             setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant') {
                    // Start streaming flag if not set
                    const isStreaming = true; 
                    return [...prev.slice(0, -1), { ...last, content: last.content + data.delta, isStreaming }];
                } else {
                    return [...prev, { role: 'assistant', content: data.delta, isStreaming: true }];
                }
             });
        }

        // Full Content Replace (Legacy/Draft)
        if (data.draft) {
             setMessages(prev => {
                // Find if we already have an assistant "draft" message
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant') {
                    // Update existing
                    const next = [...prev];
                    next[next.length - 1] = { ...last, content: data.draft };
                    return next;
                } else {
                    // Add new
                    return [...prev, { role: 'assistant', content: data.draft }];
                }
             });
        } else if (data.response) {
            // Chat response
            setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
        }

        // Citations
        if (data.citations) {
          setSources(data.citations);
        }

        // Completed
        if (data.node === 'workflow_completed') {
            eventSource.close();
            setIsLoading(false);
            addLog("Task completed.");
        }

      } catch (e) {
        console.error("Parse error", e);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE Error", err);
      eventSource.close();
      setIsLoading(false);
      addLog("Stream connection error.");
    };
  };

  const handleStop = async () => {
    if (window.currentEventSource) {
        window.currentEventSource.close();
        window.currentEventSource = null;
    }

    if (activeThreadId) {
        try {
            await stopTask(activeThreadId);
            addLog("Stop request sent to server.");
        }catch (err) {
            console.error("Failed to stop task:", err);
            addLog("Failed to send stop request to server.");
        }
    }
    setIsLoading(false);
    addLog("Task stopped Locally.");
  };

  const handleApprove = async () => {
    setIsApprovalOpen(false);
    addLog("Plan approved. Resuming...");
    try {
      await approvePlan(activeThreadId, pendingPlan);
      connectStream(activeThreadId);
    } catch (err) {
      console.error(err);
      addLog("Approval failed.");
      setIsLoading(false);
    }
  };

  const handleLoginSuccess = async (userData) => {
    setUser(userData);
    localStorage.setItem('di_user', JSON.stringify(userData));
    setShowLogin(false);
    addLog(`Logged in as ${userData.username}`);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('di_user');
    addLog("Logged out.");
  };

  // Get current report content
  const currentReport = messages.findLast(m => m.role === 'assistant')?.content || '';
  const currentUserQuery = messages.find(m => m.role === 'user')?.content || '';

  return (
    <div className="flex h-screen overflow-hidden bg-[#111111] font-sans antialiased text-gray-100">
      
      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
         {/* Navbar */}
         <header className="flex h-16 items-center justify-between border-b border-white/10 bg-[#111111] px-6 shrink-0 z-10">
            <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-lg shadow-lg shadow-blue-900/20">
                    DI
                </div>
                <span className="font-semibold text-lg tracking-tight text-white">DeepInsight <span className="text-blue-500 text-xs align-top">PRO</span></span>
            </div>
            
            <div className="flex items-center gap-4">
                 {user ? (
                     <div className="flex items-center gap-3 pl-4 border-l border-white/10">
                        <div className="text-right hidden sm:block">
                            <div className="text-xs text-gray-400">Welcome back</div>
                            <div className="text-sm font-medium text-white">{user.username}</div>
                        </div>
                        <button onClick={handleLogout} className="p-2 hover:bg-white/5 rounded-full text-gray-400 hover:text-white transition-colors">
                            <UserCircle size={20} />
                        </button>
                     </div>
                 ) : (
                    <button 
                      onClick={() => setShowLogin(true)}
                      className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm font-medium text-white transition-all hover:bg-white/10 hover:border-white/20"
                    >
                        <LogIn size={14} /> 
                        <span>Sign In</span>
                    </button>
                 )}
            </div>
         </header>

         <main className="flex flex-1 overflow-hidden relative">
            
            {/* Center Stage: Report Generation / Output */}
            <div className="flex-1 flex flex-col relative overflow-hidden">
                
                {/* 1. Empty State / Hero Input */}
                {messages.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-8 animate-in fade-in duration-500">
                        <div className="w-full max-w-2xl text-center space-y-8">
                             <div className="space-y-4">
                                <h1 className="text-4xl sm:text-5xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent pb-2">
                                    What do you want to research?
                                </h1>
                                <p className="text-lg text-gray-400 max-w-lg mx-auto">
                                    DeepInsight aggregates information from real-time web agents to generate comprehensive reports.
                                </p>
                             </div>

                             <div className="relative group">
                                <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 via-purple-600 to-blue-600 rounded-2xl opacity-20 group-hover:opacity-40 blur transition duration-500"></div>
                                <div className="relative flex items-center bg-[#1a1a1a] rounded-xl border border-white/10 p-2 shadow-2xl">
                                    <Search className="ml-3 text-gray-500" size={20} />
                                    <input 
                                        type="text" 
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                                        placeholder="Analyze the market trend of AI agents..." 
                                        className="flex-1 bg-transparent border-none px-4 py-3 text-lg text-white focus:outline-none placeholder:text-gray-600"
                                        autoFocus
                                    />
                                    <button 
                                        onClick={handleSend}
                                        disabled={!input.trim()}
                                        className="p-3 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-all shadow-lg shadow-blue-900/20"
                                    >
                                        <Send size={20} />
                                    </button>
                                </div>
                             </div>

                             {/* Suggestions */}
                             <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-8 text-left">
                                {[
                                    "Is DeepSeek V3 open source?", 
                                    "Comparison of React vs Vue in 2025", 
                                    "SpaceX Starship latest launch details"
                                ].map((q, i) => (
                                    <button 
                                        key={i}
                                        onClick={() => { setInput(q); }}
                                        className="p-4 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 hover:border-white/10 transition-all text-sm text-gray-400 hover:text-white group"
                                    >
                                        <span className="line-clamp-2">{q}</span>
                                        <ChevronRight size={14} className="mt-2 text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                                    </button>
                                ))}
                             </div>
                        </div>
                    </div>
                ) : (
                    // 2. Active Session Layout
                    <div className="flex-1 flex flex-col h-full bg-[#111111]">
                        {/* Status Bar */}
                        <div className="h-14 border-b border-white/5 flex items-center justify-between px-6 bg-[#161616] shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/5 border border-white/10 text-blue-400">
                                    <Activity size={16} />
                                </div>
                                <div className="hidden sm:block">
                                    <div className="text-xs text-gray-500 uppercase font-medium tracking-wider">Researching</div>
                                    <div className="text-sm text-white font-medium max-w-md truncate">{currentUserQuery}</div>
                                </div>
                            </div>
                            
                            <div className="flex items-center gap-3">
                                {isLoading && (
                                   <div className="flex items-center gap-2 text-xs text-blue-400 bg-blue-500/10 px-3 py-1.5 rounded-full animate-pulse">
                                       <Clock size={12} />
                                       <span className="hidden sm:inline">Processing...</span>
                                   </div>
                                )}
                                
                                <button 
                                    onClick={clearChat}
                                    className="text-xs text-gray-500 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors"
                                >
                                    New Search
                                </button>
                                
                                <button
                                    onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                                    className="p-2 hover:bg-white/5 rounded-lg text-gray-400 hover:text-white transition-colors border border-white/5"
                                    title={isSidebarOpen ? "Close Sidebar" : "Open Sidebar"}
                                >
                                    {isSidebarOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
                                </button>
                            </div>
                        </div>

                        {/* Split View Content */}
                        <div className="flex-1 overflow-hidden flex relative">
                             {/* Report Area */}
                             <div className="flex-1 flex flex-col min-w-0">
                                 <div 
                                    className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar p-6 md:p-8" 
                                    ref={reportContainerRef}
                                 >
                                    <div className="max-w-3xl mx-auto space-y-8 pb-20">
                                        {messages.length > 0 && (() => {
                                            const activeMsg = messages.findLast(m => m.role === 'assistant');
                                            if (!activeMsg) return <Loader2WithOrbit />;
                                            
                                            return (
                                                <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
                                                    
                                                    {/* 1. Thought Process Visualization - 改进版本 */}
                                                    {activeMsg.thought && (
                                                        <div className="mb-8 rounded-lg border border-cyan-500/30 bg-gradient-to-br from-cyan-500/5 to-blue-500/5 overflow-hidden">
                                                            <div className="flex items-center gap-2 px-4 py-3 border-b border-cyan-500/20 bg-cyan-500/10 text-cyan-300 text-xs font-semibold uppercase tracking-wider">
                                                                <Brain size={14} className="text-cyan-400" />
                                                                <span>System Thinking</span>
                                                            </div>
                                                            <div className="p-4 text-xs text-gray-300 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto custom-scrollbar space-y-1">
                                                                {activeMsg.thought}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* 2. Search Results Visualization - 穿插显示版本 */}
                                                    {activeMsg.searchResults && activeMsg.searchResults.length > 0 && (
                                                        <div className="mb-8">
                                                            <div className="flex items-center gap-2 mb-4 text-gray-400 text-sm font-medium">
                                                                <Sparkles size={16} className="text-cyan-400"/>
                                                                <span>Research Sources</span>
                                                            </div>
                                                            
                                                            {/* 网格布局：文本和图片穿插 */}
                                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                {activeMsg.searchResults.map((item, idx) => {
                                                                    // 文本项
                                                                    if (item.type === 'text') {
                                                                        return (
                                                                            <div key={idx} className="group">
                                                                                {/* 文本卡片 */}
                                                                                <div className="bg-gradient-to-br from-[#1a1a1a] to-[#0f0f0f] rounded-lg border border-cyan-500/20 hover:border-cyan-400/50 transition-all overflow-hidden shadow-lg hover:shadow-cyan-900/20">
                                                                                    <div className="p-4 space-y-3 border-b border-white/5">
                                                                                        <div>
                                                                                            <div className="text-xs text-cyan-400/80 mb-1 truncate font-mono">
                                                                                                {(() => {
                                                                                                    try {
                                                                                                        return new URL(item.url).hostname;
                                                                                                    } catch {
                                                                                                        return 'web';
                                                                                                    }
                                                                                                })()}
                                                                                            </div>
                                                                                            <a
                                                                                                href={item.url}
                                                                                                target="_blank"
                                                                                                rel="noopener noreferrer"
                                                                                                className="text-sm font-semibold text-gray-100 hover:text-cyan-300 transition-colors flex gap-1 items-start group/link line-clamp-2 break-all"
                                                                                            >
                                                                                                {item.title}
                                                                                                <ExternalLink size={12} className="mt-0.5 shrink-0 opacity-40 group-hover/link:opacity-100" />
                                                                                            </a>
                                                                                        </div>
                                                                                        <p className="text-xs text-gray-400 line-clamp-3 leading-relaxed">
                                                                                            {item.content}
                                                                                        </p>
                                                                                    </div>
                                                                                </div>

                                                                                {/* 关联图片：穿插显示 */}
                                                                                {item.related_images && item.related_images.length > 0 && (
                                                                                    <div className="flex gap-2 mt-3 overflow-x-auto pb-1">
                                                                                        {item.related_images.map((img, imgIdx) => (
                                                                                            <a
                                                                                                key={imgIdx}
                                                                                                href={img.url}
                                                                                                target="_blank"
                                                                                                rel="noopener noreferrer"
                                                                                                className="flex-none w-20 h-20 rounded-lg overflow-hidden border border-cyan-500/20 hover:border-cyan-400/50 transition-all group/img shadow-md hover:shadow-cyan-900/30"
                                                                                                title={img.description}
                                                                                            >
                                                                                                <img
                                                                                                    src={img.url}
                                                                                                    alt={img.description}
                                                                                                    className="w-full h-full object-cover opacity-75 group-hover/img:opacity-100 transition-opacity"
                                                                                                    onError={(e) => {
                                                                                                        e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"%3E%3Crect fill="%231a1a1a" width="100" height="100"/%3E%3Ccircle cx="50" cy="50" r="30" fill="none" stroke="%23444" stroke-width="2"/%3E%3Cpath d="M35 65 L65 35 M35 35 L65 65" stroke="%23444" stroke-width="2"/%3E%3C/svg%3E';
                                                                                                    }}
                                                                                                />
                                                                                            </a>
                                                                                        ))}
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        );
                                                                    }

                                                                    // 纯图片项
                                                                    if (item.type === 'image') {
                                                                        return (
                                                                            <div key={idx} className="h-40 rounded-lg border border-cyan-500/20 overflow-hidden hover:border-cyan-400/50 transition-all shadow-md hover:shadow-cyan-900/30">
                                                                                <a
                                                                                    href={item.url}
                                                                                    target="_blank"
                                                                                    rel="noopener noreferrer"
                                                                                    className="w-full h-full block relative group/imgcard bg-gradient-to-br from-[#1a1a1a] to-[#0f0f0f]"
                                                                                    title={item.description}
                                                                                >
                                                                                    <img
                                                                                        src={item.url}
                                                                                        alt={item.description}
                                                                                        className="w-full h-full object-cover opacity-75 group-hover/imgcard:opacity-100 transition-opacity"
                                                                                        onError={(e) => {
                                                                                            e.target.style.display = 'none';
                                                                                            e.target.parentElement.innerHTML = '<div class="w-full h-full bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-8 h-8 text-gray-600"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg></div>';
                                                                                        }}
                                                                                    />
                                                                                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover/imgcard:opacity-100 transition-opacity flex items-end p-3">
                                                                                        <span className="text-xs text-gray-200 line-clamp-2">{item.description}</span>
                                                                                    </div>
                                                                                </a>
                                                                            </div>
                                                                        );
                                                                    }

                                                                    return null;
                                                                })}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* 3. Main Report Content - 带分类样式 */}
                                                    {activeMsg.content && (
                                                        <div className="space-y-6">
                                                            <div className="flex items-center gap-2 mb-4 text-gray-300 text-sm font-semibold">
                                                                <Sparkles size={16} className="text-amber-400" />
                                                                <span>Research Report</span>
                                                            </div>
                                                            <div className="markdown-body bg-gradient-to-br from-[#1a1a1a] to-[#0f0f0f] border border-white/5 rounded-lg p-6 prose-invert prose-sm max-w-none">
                                                                <Markdown remarkPlugins={[remarkGfm]}>{activeMsg.content}</Markdown>
                                                            </div>
                                                        </div>
                                                    )}
                                                    
                                                    {isLoading && !activeMsg.content && (
                                                        <div className="mt-12 flex flex-col items-center gap-3 text-gray-500">
                                                            <div className="relative w-12 h-12 mb-2">
                                                                <div className="absolute inset-0 border-2 border-transparent border-t-cyan-400 border-r-cyan-400 rounded-full animate-spin"></div>
                                                                <div className="absolute inset-1 border-2 border-transparent border-b-purple-400 rounded-full animate-spin" style={{animationDirection: 'reverse'}}></div>
                                                            </div>
                                                            <span className="text-xs font-mono text-gray-400">Synthesizing information...</span>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })()}
                                    </div>
                                 </div>

                                 {/* Persistent Input Box with Stop Button */}
                                 <div className="p-4 border-t border-white/10 bg-[#111111] space-y-3">
                                    {/* Status Indicator */}
                                    {isLoading && (
                                        <div className="flex items-center gap-2 px-4 py-2 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
                                            <div className="flex gap-1">
                                                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{animationDelay: '0ms'}}></div>
                                                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{animationDelay: '150ms'}}></div>
                                                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{animationDelay: '300ms'}}></div>
                                            </div>
                                            <span className="text-xs text-cyan-300 font-medium">Research in progress...</span>
                                        </div>
                                    )}
                                    
                                    <div className="max-w-3xl mx-auto relative flex items-center gap-2">
                                        <div className="flex-1 relative flex items-center bg-[#1a1a1a] rounded-lg border border-white/10 p-2 shadow-2xl hover:border-white/20 transition-colors">
                                            <Search className="ml-3 text-gray-600" size={18} />
                                            <input 
                                                type="text" 
                                                value={input}
                                                onChange={(e) => setInput(e.target.value)}
                                                onKeyDown={(e) => e.key === 'Enter' && !isLoading && handleSend()}
                                                disabled={isLoading}
                                                placeholder={isLoading ? "Waiting..." : "Ask a follow-up question..."} 
                                                className="flex-1 bg-transparent border-none px-3 py-2 text-sm text-white focus:outline-none placeholder:text-gray-500 disabled:opacity-50 disabled:cursor-wait"
                                            />
                                        </div>
                                        
                                        {/* Action Buttons */}
                                        <div className="flex gap-2">
                                            {isLoading ? (
                                                <button 
                                                    onClick={handleStop}
                                                    className="p-2.5 rounded-lg bg-red-600/80 hover:bg-red-600 text-white transition-all shadow-lg hover:shadow-red-900/20 flex items-center justify-center"
                                                    title="Stop research"
                                                >
                                                    <div className="w-1.5 h-1.5 bg-white rounded" />
                                                </button>
                                            ) : (
                                                <button 
                                                    onClick={handleSend}
                                                    disabled={!input.trim()}
                                                    className="p-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white transition-all shadow-lg hover:shadow-cyan-900/20 flex items-center justify-center"
                                                    title="Send message"
                                                >
                                                    <Send size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                 </div>
                             </div>

                             {/* Right Sidebar */}
                             <div className={`transition-all duration-300 ease-in-out border-l border-white/10 bg-[#161616] flex flex-col ${isSidebarOpen ? 'w-80 opacity-100' : 'w-0 opacity-0 overflow-hidden border-l-0'}`}>
                                <ReferenceSidebar sources={sources} logs={logs} />
                             </div>
                        </div>
                    </div>
                )}
            </div>
         </main>
      </div>

      <ApprovalModal 
        isOpen={isApprovalOpen} 
        plan={pendingPlan} 
        onApprove={handleApprove} 
      />
      
      <LoginModal 
        isOpen={showLogin} 
        onLoginSuccess={handleLoginSuccess} 
        onClose={() => setShowLogin(false)} 
      />
    </div>
  );
}

// Custom Loader just for visual flair
function Loader2WithOrbit() {
    return (
        <div className="relative flex items-center justify-center h-12 w-12">
            <div className="absolute inset-0 rounded-full border-2 border-blue-500/20"></div>
            <div className="absolute inset-0 rounded-full border-t-2 border-blue-500 animate-spin"></div>
            <Bot size={20} className="text-blue-500" />
        </div>
    );
}

export default App;
