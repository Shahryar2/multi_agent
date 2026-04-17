import React, { useState, useEffect } from 'react';
import { History, Star, Trash2, Clock, Search, MessageSquare, X, ChevronRight, Loader2 } from 'lucide-react';
import { getHistory, toggleFavorite, deleteHistory } from '../lib/api';

export function HistoryPanel({ user, isOpen, onClose, onSelectHistory }) {
  const [histories, setHistories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all'); // 'all' | 'favorites'
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    if (isOpen && user) {
      loadHistories();
    }
  }, [isOpen, user]);

  const loadHistories = async () => {
    if (!user) return;
    setLoading(true);
    try {
      const data = await getHistory(user.id, user.token);
      setHistories(data);
    } catch (err) {
      console.error('Failed to load histories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleFavorite = async (e, threadId) => {
    e.stopPropagation();
    try {
      const res = await toggleFavorite(user.id, threadId, user.token);
      setHistories(prev =>
        prev.map(h =>
          h.thread_id === threadId ? { ...h, is_favorite: res.is_favorite } : h
        )
      );
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  };

  const handleDelete = async (e, threadId) => {
    e.stopPropagation();
    try {
      await deleteHistory(user.id, threadId, user.token);
      setHistories(prev => prev.filter(h => h.thread_id !== threadId));
    } catch (err) {
      console.error('Failed to delete history:', err);
    }
  };

  const getQueryFromMessages = (messages) => {
    const userMsg = messages?.find(m => m.role === 'user');
    return userMsg?.content || '未知研究主题';
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'Z');
    const now = new Date();
    const diffMs = now - date;
    const diffH = diffMs / (1000 * 60 * 60);
    if (diffH < 1) return '刚刚';
    if (diffH < 24) return `${Math.floor(diffH)}小时前`;
    const diffD = diffH / 24;
    if (diffD < 7) return `${Math.floor(diffD)}天前`;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  const filtered = histories.filter(h => {
    if (filter === 'favorites' && !h.is_favorite) return false;
    if (searchText.trim()) {
      // ✅ 改动：使用后端返回的 title 字段而非提取消息
      const title = h.title || "Untitled Session";
      if (!title.toLowerCase().includes(searchText.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div
      className={`fixed inset-0 z-50 transition-all duration-300 ${isOpen ? 'visible' : 'invisible pointer-events-none'}`}
    >
      {/* Overlay */}
      <div
        className={`absolute inset-0 bg-black/60 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`absolute left-0 top-0 h-full w-full max-w-md bg-[#161616] border-r border-white/10 shadow-2xl flex flex-col transition-transform duration-300 ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 bg-[#1a1a1a]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/30">
              <History size={18} className="text-blue-400" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">研究历史</h2>
              <p className="text-xs text-gray-500">{histories.length} 条记录</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Search & Filters */}
        <div className="px-4 py-3 border-b border-white/5 space-y-3">
          <div className="relative flex items-center">
            <Search size={14} className="absolute left-3 text-gray-500" />
            <input
              type="text"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder="搜索历史记录..."
              className="w-full bg-[#111111] border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filter === 'all'
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/5 border border-transparent'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setFilter('favorites')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1 ${
                filter === 'favorites'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/5 border border-transparent'
              }`}
            >
              <Star size={12} />
              收藏
            </button>
          </div>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-500">
              <Loader2 size={24} className="animate-spin text-blue-400" />
              <p className="text-sm mt-3">加载中...</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-500">
              <div className="mb-4 p-3 rounded-full bg-white/5 border border-white/10">
                <MessageSquare size={28} className="opacity-40" />
              </div>
              <p className="text-sm font-medium">
                {filter === 'favorites' ? '暂无收藏' : '暂无历史记录'}
              </p>
              <p className="text-xs mt-1 text-gray-600">
                {filter === 'favorites' ? '点击星标可收藏研究记录' : '开始研究后记录会出现在这里'}
              </p>
            </div>
          ) : (
            <div className="p-3 space-y-2">
              {filtered.map(h => {
                return (
                  <div
                    key={h.thread_id}
                    onClick={() => onSelectHistory(h)}
                    className="group relative p-4 rounded-xl border border-white/5 bg-[#111111] hover:bg-[#1a1a1a] hover:border-white/10 cursor-pointer transition-all"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        {/* ✅ 改动：显示后端的 title 字段 */}
                        <div className="text-sm font-medium text-white group-hover:text-blue-300 transition-colors line-clamp-2">
                          {h.title || "Untitled Session"}
                        </div>
                        {/* ✅ 改动：显示消息数和最后更新时间 */}
                        <div className="flex items-center gap-3 text-xs text-gray-500 mt-2 space-x-2">
                          <div className="flex items-center gap-1">
                            <MessageSquare size={12} />
                            <span>{h.message_count || 0} 条消息</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <Clock size={12} />
                            <span>{formatTime(h.updated_at)}</span>
                          </div>
                        </div>
                      </div>
                      <ChevronRight
                        size={16}
                        className="text-gray-600 group-hover:text-blue-400 transition-colors shrink-0 mt-0.5"
                      />
                    </div>

                    <div className="flex items-center justify-end mt-3">
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={e => handleToggleFavorite(e, h.thread_id)}
                          className={`p-1.5 rounded-lg transition-colors ${
                            h.is_favorite
                              ? 'text-amber-400 hover:bg-amber-500/10'
                              : 'text-gray-500 hover:text-amber-400 hover:bg-amber-500/10'
                          }`}
                          title={h.is_favorite ? '取消收藏' : '收藏'}
                        >
                          <Star size={14} fill={h.is_favorite ? 'currentColor' : 'none'} />
                        </button>
                        <button
                          onClick={e => handleDelete(e, h.thread_id)}
                          className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="删除"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
