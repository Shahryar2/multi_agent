import React, { useState } from 'react';
import { User, Lock, Loader2 } from 'lucide-react';
import { login, register } from '../lib/api';

export function LoginModal({ isOpen, onLoginSuccess, onClose }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      if (isLogin) {
        const user = await login(username, password);
        onLoginSuccess(user);
      } else {
        const user = await register(username, password);
        onLoginSuccess(user);
      }
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-gray-200">
        <div className="bg-blue-600 px-6 py-4 text-white">
          <h2 className="text-lg font-semibold">{isLogin ? '登录 DeepInsight' : '注册新账户'}</h2>
          <p className="text-sm text-blue-100">请登录以同步您的研究历史</p>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
              {error}
            </div>
          )}
          
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">用户名</label>
            <div className="relative">
              <User className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-lg border border-gray-300 pl-9 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="输入用户名"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-gray-300 pl-9 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="输入密码"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 flex w-full items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="animate-spin h-4 w-4" /> : (isLogin ? '登录' : '注册并登录')}
          </button>

          <div className="mt-4 text-center text-xs text-gray-500">
            {isLogin ? "还没有账号? " : "已有账号? "}
            <button
              type="button"
              onClick={() => setIsLogin(!isLogin)}
              className="text-blue-600 hover:underline"
            >
              {isLogin ? "立即注册" : "去登录"}
            </button>
            <span className="mx-2 text-gray-300">|</span>
             <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
              取消 (仅本地使用)
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
