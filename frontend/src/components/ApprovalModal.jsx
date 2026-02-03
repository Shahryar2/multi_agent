import React, { useState, useEffect } from 'react'; // 确保导入 useEffect
import { Check, X, Edit3, Trash2 } from 'lucide-react';

export function ApprovalModal({ isOpen, plan, onApprove, onReject, onUpdatePlan }) {
  const [editablePlan, setEditablePlan] = useState([]);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editText, setEditText] = useState('');

  // --- ✨ 关键修复 ---
  // 使用 useEffect 监听外部 plan prop 的变化
  useEffect(() => {
    // 当模态框打开，并且接收到了新的 plan 时，更新内部状态
    if (isOpen && plan) {
      console.log("ApprovalModal received new plan:", plan); // 添加调试日志
      setEditablePlan(plan);
    }
  }, [plan, isOpen]); // 依赖项数组是关键

  const handleEdit = (index) => {
    setEditingIndex(index);
    setEditText(editablePlan[index].description);
  };

  const handleSave = (index) => {
    const newPlan = [...editablePlan];
    newPlan[index].description = editText;
    setEditablePlan(newPlan);
    onUpdatePlan(newPlan); // 通知父组件 plan 已更新
    setEditingIndex(null);
  };

  const handleDelete = (index) => {
    const newPlan = editablePlan.filter((_, i) => i !== index);
    setEditablePlan(newPlan);
    onUpdatePlan(newPlan); // 通知父组件 plan 已更新
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in duration-300">
      <div className="bg-[#1a1a1a] border border-cyan-500/20 rounded-2xl shadow-2xl w-full max-w-2xl transform animate-in slide-in-from-bottom-10 duration-500 ease-out">
        <div className="p-6 border-b border-white/10">
          <h2 className="text-xl font-bold text-white">确认研究方向与计划</h2>
          <p className="text-sm text-gray-400 mt-1">系统已为你生成以下执行步骤，请确认无误后继续：</p>
        </div>
        
        <div className="p-6 max-h-[60vh] overflow-y-auto custom-scrollbar space-y-3">
          {editablePlan && editablePlan.length > 0 ? (
            editablePlan.map((step, index) => (
              <div key={index} className="bg-white/5 p-4 rounded-lg border border-white/10 group">
                {editingIndex === index ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="flex-1 bg-transparent border-b border-cyan-500 text-white focus:outline-none"
                      autoFocus
                    />
                    <button onClick={() => handleSave(index)} className="p-1 text-green-400 hover:bg-green-500/10 rounded">
                      <Check size={16} />
                    </button>
                    <button onClick={() => setEditingIndex(null)} className="p-1 text-gray-400 hover:bg-white/10 rounded">
                      <X size={16} />
                    </button>
                  </div>
                ) : (
                  <div className="flex justify-between items-start">
                    <p className="text-gray-300 leading-relaxed pr-4">
                      <span className="font-mono text-xs text-cyan-400 mr-2">{index + 1}.</span>
                      {step.description}
                    </p>
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleEdit(index)} className="p-1 text-cyan-400 hover:bg-cyan-500/10 rounded">
                        <Edit3 size={14} />
                      </button>
                      <button onClick={() => handleDelete(index)} className="p-1 text-red-400 hover:bg-red-500/10 rounded">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="text-center py-10">
              <p className="text-gray-500">没有规划步骤</p>
            </div>
          )}
        </div>

        <div className="p-6 bg-black/20 rounded-b-2xl flex justify-end gap-4">
          <button 
            onClick={onReject}
            className="px-6 py-2 rounded-lg text-sm font-semibold text-gray-300 bg-white/5 hover:bg-white/10 transition-colors"
          >
            拒绝并返回
          </button>
          <button 
            onClick={() => onApprove(editablePlan)}
            className="px-8 py-2 rounded-lg text-sm font-semibold text-white bg-cyan-600 hover:bg-cyan-500 transition-all shadow-lg shadow-cyan-900/30"
          >
            <Check className="inline-block mr-2" size={16} />
            批准执行
          </button>
        </div>
      </div>
    </div>
  );
}

// export default ApprovalModal;