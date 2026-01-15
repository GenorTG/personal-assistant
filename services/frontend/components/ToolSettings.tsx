'use client';

import { useState, useEffect } from 'react';
import { Settings, CheckCircle, XCircle, Loader, Zap, Search, Code, FileText, Brain, Calendar } from 'lucide-react';
import { api } from '@/lib/api';

interface Tool {
  name: string;
  description: string;
  parameters?: any;
}

const toolIcons: Record<string, any> = {
  web_search: Search,
  execute_code: Code,
  file_access: FileText,
  memory: Brain,
  calendar: Calendar,
};

export default function ToolSettings() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [enabledTools, setEnabledTools] = useState<Set<string>>(new Set());
  const [toolServiceAvailable, setToolServiceAvailable] = useState(false);

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      setLoading(true);
      const data = await api.listTools() as any;
      console.log('[ToolSettings] Received tools data:', data);
      
      const toolsList: Tool[] = Array.isArray(data?.tools) ? (data.tools as Tool[]) : [];
      console.log('[ToolSettings] Parsed tools list:', toolsList.map(t => ({ name: t.name, hasDescription: !!t.description })));
      
      // Validate tools have required fields
      const validTools = toolsList.filter(t => t.name && t.name.trim() !== '');
      if (validTools.length !== toolsList.length) {
        console.warn('[ToolSettings] Some tools missing name field:', toolsList.filter(t => !t.name || t.name.trim() === ''));
      }
      
      setTools(validTools);
      
      // Check if tool service is available
      setToolServiceAvailable(validTools.length > 0);
      
      // Initialize all tools as enabled by default
      const enabled = new Set<string>(validTools.map((t: Tool) => String(t.name)));
      setEnabledTools(enabled);
    } catch (error) {
      console.error('[ToolSettings] Error loading tools:', error);
      setToolServiceAvailable(false);
    } finally {
      setLoading(false);
    }
  };

  const toggleTool = (toolName: string) => {
    setEnabledTools((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(toolName)) {
        newSet.delete(toolName);
      } else {
        newSet.add(toolName);
      }
      return newSet;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader className="animate-spin text-blue-500" size={24} />
        <span className="ml-2 text-gray-600">Loading tools...</span>
      </div>
    );
  }

  if (!toolServiceAvailable) {
    return (
      <div className="p-4 border border-yellow-200 rounded bg-yellow-50">
        <div className="flex items-center gap-2 text-yellow-800">
          <XCircle size={20} />
          <div>
            <div className="font-medium">Tool Service Unavailable</div>
            <div className="text-sm mt-1">
              The Tool Service is not running. Please start it via the launcher to enable tool functionality.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg flex items-center gap-2">
          <Zap size={20} />
          Available Tools
        </h3>
        <div className="text-sm text-gray-500">
          {enabledTools.size} of {tools.length} enabled
        </div>
      </div>

      <div className="space-y-2">
        {tools.map((tool) => {
          const Icon = toolIcons[tool.name] || Settings;
          const isEnabled = enabledTools.has(tool.name);

          return (
            <div
              key={tool.name}
              className={`p-4 border rounded transition-all ${
                isEnabled
                  ? 'border-blue-300 bg-blue-50'
                  : 'border-gray-200 bg-gray-50'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3 flex-1">
                  <div className={`p-2 rounded ${
                    isEnabled ? 'bg-blue-100' : 'bg-gray-200'
                  }`}>
                    <Icon
                      size={20}
                      className={isEnabled ? 'text-blue-600' : 'text-gray-500'}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-medium text-gray-900 capitalize">
                        {tool?.name?.replace(/_/g, ' ') || 'Unknown Tool'}
                      </h4>
                      {isEnabled ? (
                        <CheckCircle size={16} className="text-green-500" />
                      ) : (
                        <XCircle size={16} className="text-gray-400" />
                      )}
                    </div>
                    <p className="text-sm text-gray-600 mb-2">
                      {tool?.description || 'No description available'}
                    </p>
                    {tool.parameters && (
                      <div className="text-xs text-gray-500 bg-white p-2 rounded border border-gray-200 mt-2">
                        <div className="font-medium mb-1">Parameters:</div>
                        <div className="space-y-1">
                          {Object.entries(tool.parameters.properties || {}).map(([key, value]: [string, any]) => (
                            <div key={key} className="flex gap-2">
                              <span className="font-mono text-blue-600">{key}:</span>
                              <span className="text-gray-600">{value.type || 'any'}</span>
                              {value.description && (
                                <span className="text-gray-500">- {value.description}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer ml-4">
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={() => toggleTool(tool.name)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {tools.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No tools available
        </div>
      )}
    </div>
  );
}

