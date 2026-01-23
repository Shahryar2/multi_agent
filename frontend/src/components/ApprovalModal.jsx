import React, { useState } from 'react';
import { CheckCircle2, AlertCircle, Edit2, RotateCcw, X } from 'lucide-react';

export function ApprovalModal({ isOpen, plan, onApprove, onReject, onModify }) {
  const [editingStep, setEditingStep] = useState(null);
  const [editedPlan, setEditedPlan] = useState(plan || []);

  if (!isOpen) return null;

  const handleStepEdit = (index, newDescription) => {
    const updated = [...editedPlan];
    updated[index].description = newDescription;
    setEditedPlan(updated);
  };

  const handleApprove = () => {
    onApprove(editedPlan);
    setEditedPlan(plan);
    setEditingStep(null);
  };

  const handleReject = () => {
    if (onReject) {
      onReject();
      setEditedPlan(plan);
      setEditingStep(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-2xl overflow-hidden rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0f0f0f] shadow-2xl border border-cyan-500/30">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-cyan-500/20 bg-cyan-500/10 px-6 py-4">
          <div className="flex items-center gap-3 text-cyan-300">
            <AlertCircle size={20} className="text-cyan-400" />
            <h3 className="font-bold text-lg">确认研究方向与计划</h3>
          </div>
          <span className="text-xs font-semibold text-cyan-400/70 uppercase tracking-wider">执行前审批</span>
        </div>

        {/* Content */}
        <div className="px-6 py-5">
          <p className="mb-4 text-sm text-gray-400">系统已为你生成以下执行步骤，请确认无误后继续：</p>
          
          <div className="max-h-[50vh] overflow-y-auto space-y-2 rounded-lg border border-cyan-500/20 bg-[#0f0f0f]/50 p-3">
            {editedPlan.map((step, i) => (
              <div 
                key={i} 
                className="flex gap-3 rounded-lg bg-[#1a1a1a] p-4 border border-white/5 hover:border-cyan-500/30 transition-colors group"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan-500/20 text-xs font-bold text-cyan-300 border border-cyan-500/40">
                  {i + 1}
                </span>
                <div className="flex-1 space-y-2">
                  {editingStep === i ? (
                    <input
                      type="text"
                      value={editedPlan[i].description}
                      onChange={(e) => handleStepEdit(i, e.target.value)}
                      className="w-full bg-[#0f0f0f] border border-cyan-500/40 rounded px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-cyan-400/70 focus:ring-1 focus:ring-cyan-400/20"
                      autoFocus
                    />
                  ) : (
                    <div className="text-sm font-medium text-gray-100">{step.description}</div>
                  )}
                  <div className="flex gap-2 items-center">
                    <span className="inline-flex items-center rounded-md bg-cyan-500/15 px-2.5 py-1 text-xs font-semibold text-cyan-300 border border-cyan-500/30 uppercase tracking-widest">
                      {step.type}
                    </span>
                    {step.status && (
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        step.status === 'pending' 
                          ? 'bg-gray-500/20 text-gray-300' 
                          : 'bg-green-500/20 text-green-300'
                      }`}>
                        {step.status}
                      </span>
                    )}
                  </div>
                </div>
                
                {/* Edit Button */}
                {editingStep !== i && (
                  <button
                    onClick={() => setEditingStep(i)}
                    className="p-2 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/5 text-gray-400 hover:text-cyan-300"
                    title="Edit step"
                  >
                    <Edit2 size={14} />
                  </button>
                )}
                
                {/* Save/Cancel for edit */}
                {editingStep === i && (
                  <button
                    onClick={() => setEditingStep(null)}
                    className="p-2 rounded bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30"
                  >
                    <CheckCircle2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
          
          {editedPlan.length === 0 && (
            <div className="text-center py-8 text-gray-500 text-sm">
              没有规划步骤
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-cyan-500/20 bg-[#0f0f0f]/50 px-6 py-4">
          {onReject && (
            <button 
              onClick={handleReject}
              className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm font-semibold text-red-300 transition-all hover:bg-red-500/20 hover:border-red-500/50 focus:outline-none focus:ring-2 focus:ring-red-500/30"
            >
              <RotateCcw size={16} />
              打回重新规划
            </button>
          )}
          
          <button 
            onClick={handleApprove}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-600 to-cyan-500 px-6 py-2.5 text-sm font-semibold text-white transition-all hover:from-cyan-500 hover:to-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 shadow-lg hover:shadow-cyan-900/30"
          >
            <CheckCircle2 size={16} />
            批准执行
          </button>
        </div>
      </div>
    </div>
  );
}
