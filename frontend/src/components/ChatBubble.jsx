import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { clsx } from 'clsx';
import { Bot, User,  Loader2 } from 'lucide-react';

export function ChatBubble({ role, content, isLoading }) {
  const isAssistant = role === 'assistant';

  return (
    <div className={clsx(
      "flex w-full items-start gap-4 p-4",
      isAssistant ? "justify-start" : "justify-end"
    )}>
      {isAssistant && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white">
          <Bot size={16} />
        </div>
      )}

      <div className={clsx(
        "relative max-w-3xl overflow-hidden rounded-2xl px-5 py-3.5 text-sm leading-6 shadow-sm",
        isAssistant 
          ? "bg-white text-gray-900 border border-gray-100" 
          : "bg-blue-600 text-white"
      )}>
        {isLoading ? (
           <div className="flex items-center gap-1 h-6">
             <span className="animate-blink h-1.5 w-1.5 rounded-full bg-current opacity-20"></span>
             <span className="animate-blink h-1.5 w-1.5 rounded-full bg-current opacity-20 delay-200"></span>
             <span className="animate-blink h-1.5 w-1.5 rounded-full bg-current opacity-20 delay-400"></span>
           </div>
        ) : (
          <div className={clsx("markdown-body", !isAssistant && "text-white")}>
            {isAssistant ? (
               <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
            ) : (
               <p className="whitespace-pre-wrap">{content}</p>
            )}
          </div>
        )}
      </div>

      {!isAssistant && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-200 text-gray-500">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
