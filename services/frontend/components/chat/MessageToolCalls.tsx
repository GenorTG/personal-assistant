'use client';

import { useState } from 'react';
import { Search, Code, FileText, Brain, Calendar, Zap, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface MessageToolCallsProps {
  toolCalls: any[];
}

const toolIcons: Record<string, any> = {
  google_search: Search,
  web_search: Search,
  execute_code: Code,
  file_access: FileText,
  memory: Brain,
  calendar: Calendar,
  get_current_time: Zap,
  call_webhook: Zap,
};

export function MessageToolCalls({ toolCalls }: MessageToolCallsProps) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  if (!toolCalls || toolCalls.length === 0) return null;

  const toggleExpand = (idx: number) => {
    setExpanded(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <div className="mb-2 space-y-1 max-w-3xl">
      {toolCalls.map((toolCall: any, toolIdx: number) => {
        const ToolIcon = toolIcons[toolCall.name] || Zap;
        const isExpanded = expanded[toolIdx];
        const hasSuccess = toolCall.success === true || (toolCall.result && !toolCall.error);
        const hasError = toolCall.error || (toolCall.success === false);
        const hasArguments = toolCall.arguments && Object.keys(toolCall.arguments).length > 0;
        const hasDetails = hasArguments || toolCall.result || toolCall.error;

        return (
          <div
            key={toolIdx}
            className="px-3 py-2 bg-purple-50 border border-purple-200 rounded text-xs"
          >
            <div className="flex items-center gap-2">
              <ToolIcon size={14} className="text-purple-600 flex-shrink-0" />
              <span className="text-purple-700 font-medium capitalize">
                {toolCall.name?.replace(/_/g, ' ') || 'Tool'}
              </span>
              {hasSuccess && (
                <span className="ml-auto text-green-600 font-medium flex items-center gap-1">
                  <span className="text-green-500">✓</span> Executed
                </span>
              )}
              {hasError && (
                <span className="ml-auto text-red-600 font-medium flex items-center gap-1">
                  <span className="text-red-500">✗</span> Failed
                </span>
              )}
              {!hasSuccess && !hasError && (
                <span className="ml-auto text-gray-500 text-xs">Pending</span>
              )}
              {hasDetails && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0 ml-1"
                  onClick={() => toggleExpand(toolIdx)}
                >
                  {isExpanded ? (
                    <ChevronUp size={12} className="text-purple-600" />
                  ) : (
                    <ChevronDown size={12} className="text-purple-600" />
                  )}
                </Button>
              )}
            </div>
            {isExpanded && hasDetails && (
              <div className="mt-2 pt-2 border-t border-purple-200 space-y-2">
                {hasArguments && (
                  <div>
                    <div className="text-purple-600 font-medium mb-1">Arguments:</div>
                    <pre className="text-xs bg-white p-2 rounded border border-purple-100 overflow-x-auto max-w-full">
                      {JSON.stringify(toolCall.arguments, null, 2)}
                    </pre>
                  </div>
                )}
                {toolCall.result && (
                  <div>
                    <div className="text-green-600 font-medium mb-1">Result:</div>
                    <pre className="text-xs bg-white p-2 rounded border border-green-100 overflow-x-auto max-w-full">
                      {typeof toolCall.result === 'string' 
                        ? toolCall.result 
                        : JSON.stringify(toolCall.result, null, 2)}
                    </pre>
                  </div>
                )}
                {toolCall.error && (
                  <div>
                    <div className="text-red-600 font-medium mb-1">Error:</div>
                    <div className="text-xs bg-red-50 p-2 rounded border border-red-200 text-red-700">
                      {toolCall.error}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}




