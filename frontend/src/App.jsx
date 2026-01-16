// src/App.jsx
import React, { useState, useRef, useEffect } from 'react';
import { Send, LogIn, UserCircle } from 'lucide-react';
import { ChatBubble } from './components/ChatBubble';
import { ReferenceSidebar } from './components/ReferenceSidebar';
import { ApprovalModal } from './components/ApprovalModal';
import { LoginModal } from './components/LoginModal';
import { startTask, approvePlan, login, syncHistory, getHistory, API_BASE } from './lib/api';

function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('di_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [showLogin, setShowLogin] = useState(false);
  
  // Load initial state from localStorage if available
  const [messages, setMessages] = useState(() => {
    const saved = localStorage.getItem('di_messages');
    return saved ? JSON.parse(saved) : [
      { role: 'assistant', content: '👋 你好！我是 DeepInsight 全栈研究助手。请告诉我你想研究的主题。' }
    ];
  });
  
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sources, setSources] = useState([]);
  const [logs, setLogs] = useState([]);
  
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
    if (user && activeThreadId && messages.length > 1) {
        const timeout = setTimeout(() => {
            syncHistory(user.id, activeThreadId, messages).catch(console.error);
        }, 2000); // Debounce
        return () => clearTimeout(timeout);
    }
  }, [activeThreadId, messages, user]);

  // Load history on login
  const handleLoginSuccess = async (userData) => {
    setUser(userData);
    localStorage.setItem('di_user', JSON.stringify(userData));
    setShowLogin(false);
    addLog(`Logged in as ${userData.username}`);
    // Load latest history if strictly needed, or just keep current session
    // For now, let's merge or load? Let's just keep current but enable sync.
    // If current is empty, load from server?
    if (messages.length <= 1) {
        try {
            const histories = await getHistory(userData.id);
            if (histories.length > 0) {
                const latest = histories[0];
                setMessages(latest.messages);
                setActiveThreadId(latest.thread_id);
                addLog("Restored history from cloud.");
            }
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('di_user');
    addLog("Logged out.");
  };

  const messagesEndRef = useRef(null);

  // Auto-scroll
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString([], { hour12: false });
    setLogs(prev => [...prev, `[${time}] ${msg}`]);
  };

  // Clear Chat Function
  const clearChat = () => {
    setMessages([{ role: 'assistant', content: '👋 你好！我是 DeepInsight 全栈研究助手。请告诉我你想研究的主题。' }]);
    setSources([]);
    setLogs([]);
    setPendingPlan([]);
    setActiveThreadId(null);
    localStorage.removeItem('di_messages');
    localStorage.removeItem('di_thread_id');
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const query = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: query }]);
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
    
    // Placeholder message for streaming content
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    eventSource.onmessage = (event) => {
      if (event.data === "[DONE]") {
        eventSource.close();
        setIsLoading(false);
        setMessages(prev => {
           const newParams = [...prev];
           const last = newParams[newParams.length-1];
           if(last.isStreaming) last.isStreaming = false;
           return newParams;
        });
        addLog("Stream ended.");
        return;
      }

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

        // Content Update (Draft or Response)
        const text = data.draft || data.response;
        if (text) {
          setMessages(prev => {
            const next = [...prev];
            const lastMsg = next[next.length - 1];
            if (lastMsg.role === 'assistant') {
              lastMsg.content = text;
            }
            return next;
          });
        }

        // Citations
        if (data.citations) {
          setSources(data.citations);
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

  const handleApprove = async () => {
    setIsApprovalOpen(false);
    addLog("Plan approved. Resuming...");
    
    // Optimistic UI
    setMessages(prev => [...prev, { role: 'assistant', content: '✅ 计划已确认，正在继续执行...', isStreaming: true }]);
    
    try {
      await approvePlan(activeThreadId, pendingPlan);
      // Reconnect stream to continue
      connectStream(activeThreadId);
    } catch (err) {
      console.error(err);
      addLog("Approval failed.");
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-white font-sans antialiased text-gray-900">
      <ReferenceSidebar sources={sources} logs={logs} onClear={clearChat} />

      <main className="flex flex-1 flex-col relative min-w-0">
        {/* Header */}
        <header className="flex h-14 items-center justify-between border-b border-gray-100 px-6 bg-white shrink-0">
          <div className="flex items-center gap-2 font-bold text-gray-800">
            <span className="text-xl">🦁</span>
            <span>DeepInsight Pro</span>
          </div>
          <div className="flex items-center gap-4">
             <div className="text-xs text-gray-400">Powered by LangGraph</div>
             {user ? (
                 <div className="flex items-center gap-2 text-sm text-gray-600">
                    <UserCircle size={16} />
                    <span>{user.username}</span>
                    <button onClick={handleLogout} className="text-xs text-red-400 hover:text-red-600 ml-1">退出</button>
                 </div>
             ) : (
                <button 
                  onClick={() => setShowLogin(true)}
                  className="flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700"
                >
                    <LogIn size={14} /> 登录 / 注册
                </button>
             )}
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto bg-gray-50/50 p-4 pb-24">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.map((msg, idx) => (
              <ChatBubble 
                key={idx} 
                role={msg.role} 
                content={msg.content} 
                isLoading={msg.role === 'assistant' && msg.content === '' && isLoading}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white to-transparent pt-10 pb-6 px-4">
          <div className="mx-auto max-w-3xl">
             <div className="relative flex items-center gap-2 rounded-2xl border border-gray-200 bg-white p-2 shadow-sm ring-1 ring-gray-200 focus-within:ring-2 focus-within:ring-blue-500">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                  placeholder="输入研究课题..."
                  disabled={isLoading}
                  className="flex-1 border-none bg-transparent px-4 py-2 text-sm focus:outline-none disabled:opacity-50"
                  autoFocus
                />
                <button 
                  onClick={handleSend}
                  disabled={isLoading || !input.trim()}
                  className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white transition-all hover:bg-blue-700 disabled:opacity-50 disabled:bg-gray-300"
                >
                  <Send size={16} />
                </button>
             </div>
          </div>
        </div>
      </main>

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

export default App;
