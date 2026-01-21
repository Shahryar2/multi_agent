import React, { useState, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Send, LogIn, UserCircle, Bot, Activity, Clock, Search, ChevronRight, Loader2, PanelRightClose, PanelRightOpen, Brain, Sparkles, Image, ExternalLink } from 'lucide-react';
import { ReferenceSidebar } from './components/ReferenceSidebar';
import { ApprovalModal } from './components/ApprovalModal';
import { LoginModal } from './components/LoginModal';
import { startTask, approvePlan, syncHistory, getHistory, API_BASE } from './lib/api';

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
  
  // Persist messages
  useEffect(() => {
    localStorage.setItem('di_messages', JSON.stringify(messages));
  }, [messages]);

  // Approval State
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(() => localStorage.getItem('di_thread_id'));

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
    setMessages([{ role: 'user', content: query }]);
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
        
        // Interrupt
        if (data.type === 'interrupt') {
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
                return prev; 
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

  const handleStop = () => {
    if (window.currentEventSource) {
        window.currentEventSource.close();
        window.currentEventSource = null;
        setIsLoading(false);
        addLog("Task stopped by user.");
    }
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
                                    className="flex-1 overflow-y-auto custom-scrollbar p-6 md:p-8" 
                                    ref={reportContainerRef}
                                 >
                                    <div className="max-w-3xl mx-auto space-y-8 pb-20">
                                        {messages.length > 0 && (() => {
                                            const activeMsg = messages.findLast(m => m.role === 'assistant');
                                            if (!activeMsg) return <Loader2WithOrbit />;
                                            
                                            return (
                                                <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
                                                    
                                                    {/* 1. Thought Process Visualization */}
                                                    {activeMsg.thought && (
                                                        <div className="mb-6 rounded-xl border border-blue-500/20 bg-blue-500/5 overflow-hidden">
                                                            <div className="flex items-center gap-2 px-4 py-2 border-b border-blue-500/10 bg-blue-500/10 text-blue-400 text-xs font-medium uppercase tracking-wider">
                                                                <Brain size={14} />
                                                                <span>Thinking Process</span>
                                                            </div>
                                                            <div className="p-4 text-sm text-gray-300 font-mono whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto custom-scrollbar">
                                                                {activeMsg.thought}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* 2. Search Results Visualization */}
                                                    {activeMsg.searchResults && activeMsg.searchResults.length > 0 && (
                                                        <div className="mb-8">
                                                            <div className="flex items-center gap-2 mb-3 text-gray-400 text-sm font-medium">
                                                                <Sparkles size={16} className="text-purple-400"/>
                                                                <span>Sources Found</span>
                                                            </div>
                                                            <div className="flex gap-4 overflow-x-auto pb-4 custom-scrollbar snap-x">
                                                                {activeMsg.searchResults.map((item, idx) => (
                                                                    <div key={idx} className="flex-none w-60 bg-[#1a1a1a] rounded-xl border border-white/10 overflow-hidden hover:border-white/20 transition-all snap-start">
                                                                        {item.images && item.images.length > 0 ? (
                                                                            <div className="h-32 bg-gray-800 relative">
                                                                                <img src={item.images[0]} alt="" className="w-full h-full object-cover opacity-80 hover:opacity-100 transition-opacity" />
                                                                            </div>
                                                                        ) : (
                                                                            <div className="h-32 bg-gray-800 flex items-center justify-center text-gray-600">
                                                                                <Image size={24} />
                                                                            </div>
                                                                        )}
                                                                        <div className="p-3">
                                                                            <div className="text-xs text-blue-400 mb-1 truncate">{(() => { try { return new URL(item.url).hostname } catch { return 'web' } })()}</div>
                                                                            <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-gray-200 line-clamp-2 hover:text-blue-400 transition-colors flex gap-1 items-start">
                                                                                {item.title}
                                                                                <ExternalLink size={10} className="mt-1 shrink-0 opacity-50" />
                                                                            </a>
                                                                        </div>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* 3. Main Report Content */}
                                                    {activeMsg.content && (
                                                        <div className="markdown-body">
                                                            <Markdown remarkPlugins={[remarkGfm]}>{activeMsg.content}</Markdown>
                                                        </div>
                                                    )}
                                                    
                                                    {isLoading && !activeMsg.content && (
                                                        <div className="mt-8 flex flex-col items-center gap-2 text-gray-500 opacity-50">
                                                            <Loader2 className="animate-spin" />
                                                            <span className="text-xs font-mono">Synthesizing information...</span>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })()}
                                    </div>
                                 </div>

                                 {/* Persistent Input Box */}
                                 <div className="p-4 border-t border-white/10 bg-[#111111]">
                                    <div className="max-w-3xl mx-auto relative flex items-center bg-[#1a1a1a] rounded-xl border border-white/10 p-2 shadow-2xl">
                                        <Search className="ml-3 text-gray-500" size={20} />
                                        <input 
                                            type="text" 
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                                            disabled={isLoading}
                                            placeholder={isLoading ? "Research in progress..." : "Ask a follow-up question..."} 
                                            className="flex-1 bg-transparent border-none px-4 py-2 text-white focus:outline-none placeholder:text-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                        />
                                        <button 
                                            onClick={handleSend}
                                            disabled={!input.trim() || isLoading}
                                            className="p-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-all"
                                        >
                                            <Send size={16} />
                                        </button>
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
