// src/App.jsx
import React, { useState, useRef, useEffect } from 'react';
import { Send, Terminal } from 'lucide-react';
import { ChatBubble } from './components/ChatBubble';
import { ReferenceSidebar } from './components/ReferenceSidebar';
import { ApprovalModal } from './components/ApprovalModal';
import { startTask, approvePlan, API_BASE } from './lib/api';

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '👋 你好！我是 DeepInsight 全栈研究助手。请告诉我你想研究的主题。' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sources, setSources] = useState([]);
  const [logs, setLogs] = useState([]);
  
  // Approval State
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);

  const messagesEndRef = useRef(null);
  const logsEndRef = useRef(null);

  // Auto-scroll
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString([], { hour12: false });
    setLogs(prev => [...prev, `[${time}] ${msg}`]);
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const query = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setIsLoading(true);
    addLog(`Starting task: ${query.substring(0, 20)}...`);

    try {
      const { thread_id } = await startTask(query);
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
      <ReferenceSidebar sources={sources} />

      <main className="flex flex-1 flex-col relative min-w-0">
        {/* Header */}
        <header className="flex h-14 items-center justify-between border-b border-gray-100 px-6 bg-white shrink-0">
          <div className="flex items-center gap-2 font-bold text-gray-800">
            <span className="text-xl">🦁</span>
            <span>DeepInsight Pro</span>
          </div>
          <div className="text-xs text-gray-400">Powered by LangGraph</div>
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
             
             {/* Mini Logs */}
             <div className="mt-2 h-20 overflow-hidden rounded-lg bg-gray-900 p-2 text-[10px] text-gray-400 font-mono opacity-60 hover:opacity-100 transition-opacity">
                <div className="flex items-center gap-2 mb-1 border-b border-gray-800 pb-1">
                  <Terminal size={10} /> <span>System Logs</span>
                </div>
                <div className="h-full overflow-y-auto pb-4">
                  {logs.map((log, i) => (
                    <div key={i} className="truncate">{log}</div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
             </div>
          </div>
        </div>
      </main>

      <ApprovalModal 
        isOpen={isApprovalOpen} 
        plan={pendingPlan} 
        onApprove={handleApprove} 
      />
    </div>
  );
}

export default App;
