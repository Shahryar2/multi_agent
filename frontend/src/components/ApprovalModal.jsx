import React from 'react';
import { CheckCircle2, AlertCircle } from 'lucide-react';

export function ApprovalModal({ isOpen, plan, onApprove }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-gray-200">
        <div className="flex items-center justify-between border-b border-gray-100 bg-amber-50 px-6 py-4">
          <div className="flex items-center gap-2 text-amber-800">
            <AlertCircle size={20} />
            <h3 className="font-bold">需要确认计划</h3>
          </div>
          <span className="text-xs font-semibold text-amber-600 uppercase tracking-wider">Approval Required</span>
        </div>

        <div className="px-6 py-4">
          <p className="mb-4 text-sm text-gray-500">为了确保研究方向准确，请确认系统生成的以下执行步骤：</p>
          
          <div className="max-h-[60vh] overflow-y-auto space-y-2 rounded-lg border border-gray-100 bg-gray-50 p-2">
            {plan.map((step, i) => (
              <div key={i} className="flex gap-3 rounded-md bg-white p-3 shadow-sm border border-gray-100">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">
                  {i + 1}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900">{step.description}</div>
                  <div className="mt-1 flex gap-2">
                    <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 ring-1 ring-inset ring-gray-500/10 uppercase">
                      {step.type}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-gray-100 bg-gray-50 px-6 py-4">
          <button 
            onClick={onApprove}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <CheckCircle2 size={16} />
            批准并执行
          </button>
        </div>
      </div>
    </div>
  );
}
