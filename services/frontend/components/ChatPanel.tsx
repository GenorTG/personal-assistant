'use client';

import { useState, useEffect, useRef } from 'react';
import { Send, Mic, Volume2, Zap, Search, Code, FileText, Brain, Calendar, Info, Paperclip, X, Square, RefreshCw, Edit2, Check, X as XIcon } from 'lucide-react';
import { api } from '@/lib/api';
import { useSamplerSettings } from '@/contexts/SamplerSettingsContext';
import { useSettings } from '@/contexts/SettingsContext';
import { formatError, isNotFoundError, showError } from '@/lib/utils';
import AudioVisualizer from './AudioVisualizer';

interface ChatPanelProps {
  conversationId: string | null;
  onConversationNotFound?: (conversationId: string) => void;
  onConversationCreated?: (conversationId: string) => void;
}

export default function ChatPanel({ conversationId, onConversationNotFound, onConversationCreated }: ChatPanelProps) {
  const { settings: samplerSettings } = useSamplerSettings();
  const { userName: contextUserName, botName: contextBotName } = useSettings();
  
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editContent, setEditContent] = useState<string>('');
  const [recording, setRecording] = useState(false);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [userName, setUserName] = useState<string>(contextUserName || 'You');
  const [botName, setBotName] = useState<string>(contextBotName || 'Assistant');
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Update names when context changes
  useEffect(() => {
    if (contextUserName) setUserName(contextUserName);
    if (contextBotName) setBotName(contextBotName);
  }, [contextUserName, contextBotName]);

  useEffect(() => {
    if (conversationId) {
      loadConversation();
    } else {
      setMessages([]);
    }
  }, [conversationId]);

  // User names are now managed by SettingsContext
  // No need for separate loadUserNames function

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadConversation = async () => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    try {
      const conv = await api.getConversation(conversationId) as any;
      setMessages(conv.messages || []);
    } catch (error: any) {
      console.error('Error loading conversation:', error);
      
      // Check if it's a 404 (conversation not found)
      if (isNotFoundError(error)) {
        // Conversation not found, will be removed from list
        // Notify parent to remove this conversation
        if (onConversationNotFound) {
          onConversationNotFound(conversationId);
        }
      }
      
      // Clear messages for any error
      setMessages([]);
    }
  };

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const fileArray = Array.from(files);
    
    // Upload files to data/files/
    for (const file of fileArray) {
      try {
        await api.uploadFile(file);
        setUploadedFiles((prev) => [...prev, file]);
      } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
        showError(formatError(error), `Error uploading ${file.name}`);
      }
    }
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleStop = () => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!conversationId || loading) return;
    
    setLoading(true);
    try {
      const response = await api.regenerateLastResponse(
        conversationId,
        samplerSettings
      ) as any;
      
      // Remove the last assistant message from local state (if any)
      setMessages((prev) => {
        // Find last assistant message and remove it
        let lastAssistantIdx = prev.length - 1;
        while (lastAssistantIdx >= 0 && prev[lastAssistantIdx].role !== 'assistant') {
          lastAssistantIdx--;
        }
        if (lastAssistantIdx >= 0) {
          return prev.slice(0, lastAssistantIdx);
        }
        return prev;
      });
      
      // Add the new regenerated response
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        tool_calls: response.tool_calls || [],
        context_used: response.context_used || [],
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error regenerating:', error);
      showError(formatError(error), 'Error regenerating response');
    } finally {
      setLoading(false);
    }
  };

  const handleStartEdit = (index: number) => {
    setEditingIndex(index);
    setEditContent(messages[index].content);
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditContent('');
  };

  const handleSaveEdit = async () => {
    if (editingIndex === null || !conversationId) return;
    
    const message = messages[editingIndex];
    try {
      await api.updateMessage(
        conversationId,
        editingIndex,
        editContent,
        message.role
      );
      
      // Update local state
      setMessages((prev) => {
        const updated = [...prev];
        updated[editingIndex] = { ...updated[editingIndex], content: editContent };
        return updated;
      });
      
      setEditingIndex(null);
      setEditContent('');
      
      // If we edited the last user message, we might want to regenerate
      // But for now, just save the edit
    } catch (error) {
      console.error('Error updating message:', error);
      showError(formatError(error), 'Error updating message');
    }
  };

  const handleSend = async () => {
    if ((!input.trim() && uploadedFiles.length === 0) || loading) return;

    let userMessage = input.trim();
    
    // Add file references to message
    if (uploadedFiles.length > 0) {
      const fileNames = uploadedFiles.map(f => f.name).join(', ');
      userMessage = userMessage 
        ? `${userMessage}\n\n[Files: ${fileNames}]`
        : `[Files: ${fileNames}]`;
    }

    setInput('');
    setUploadedFiles([]);
    setLoading(true);

    // Create abort controller for this request
    const controller = new AbortController();
    setAbortController(controller);

    // Add user message immediately
    const newUserMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
      files: uploadedFiles.map(f => ({ name: f.name, size: f.size, type: f.type })),
    };
    setMessages((prev) => [...prev, newUserMessage]);

    try {
      // Send message with current sampler settings from context
      const response = await api.sendMessage(
        userMessage, 
        conversationId || undefined,
        samplerSettings,
        controller
      ) as any;
      
      // Update conversation ID if new conversation was created
      if (response.conversation_id && response.conversation_id !== conversationId) {
        // Notify parent to update conversation list
        if (onConversationCreated) {
          onConversationCreated(response.conversation_id);
        }
      }

      // Add assistant response with tool calls and context
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        tool_calls: response.tool_calls || [],
        context_used: response.context_used || [],
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error: any) {
      // Don't show error if it was a cancellation
      if (error.name !== 'AbortError') {
        console.error('Error sending message:', error);
        showError(formatError(error), 'Error sending message');
        // Remove the user message if request failed (unless it was cancelled)
        setMessages((prev) => prev.slice(0, -1));
      }
    } finally {
      setLoading(false);
      setAbortController(null);
    }
  };

  const handleTTS = async (text: string) => {
    try {
      const audioBlob = await api.textToSpeech(text);
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      await audio.play();
      audio.onended = () => URL.revokeObjectURL(audioUrl);
    } catch (error) {
      console.error('Error with TTS:', error);
      alert('Failed to play text-to-speech');
    }
  };

  const handleSTT = async () => {
    if (recording) {
      // Stop recording
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
        setRecording(false);
      }
    } else {
      // Start recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
        const mediaRecorder = new MediaRecorder(stream);
        const chunks: Blob[] = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) {
            chunks.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          setAudioStream(null); // Clear visualizer
          const audioBlob = new Blob(chunks, { type: 'audio/wav' });
          try {
            const result = await api.speechToText(audioBlob);
            setInput(result.text);
          } catch (error) {
            console.error('Error with STT:', error);
            alert('Error transcribing audio');
          }
          stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        mediaRecorderRef.current = mediaRecorder;
        setRecording(true);
      } catch (error) {
        console.error('Error starting recording:', error);
        alert('Error accessing microphone');
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-white">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 mt-8">
            Start a conversation by sending a message
          </div>
        ) : (
          messages.map((msg, idx) => {
            const isUser = msg.role === 'user';
            const displayName = isUser ? userName : botName;
            const toolCalls = msg.tool_calls || [];
            const contextUsed = msg.context_used || [];
            
            const toolIcons: Record<string, any> = {
              web_search: Search,
              execute_code: Code,
              file_access: FileText,
              memory: Brain,
              calendar: Calendar,
            };
            
            return (
            <div
              key={idx}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-4`}
              >
                {/* Username label */}
                <span
                  className={`text-xs font-medium mb-1 px-2 ${
                    isUser ? 'text-primary-600' : 'text-gray-600'
                  }`}
            >
                  {displayName}
                </span>
                
                {/* Context indicator */}
                {!isUser && contextUsed.length > 0 && (
                  <div className="mb-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-700 flex items-center gap-2 max-w-3xl">
                    <Info size={14} />
                    <span>Used {contextUsed.length} relevant context{contextUsed.length > 1 ? 's' : ''} from past conversations</span>
                  </div>
                )}
                
                {/* Tool calls indicator */}
                {!isUser && toolCalls.length > 0 && (
                  <div className="mb-2 space-y-1 max-w-3xl">
                    {toolCalls.map((toolCall: any, toolIdx: number) => {
                      const ToolIcon = toolIcons[toolCall.name] || Zap;
                      return (
                        <div
                          key={toolIdx}
                          className="px-3 py-2 bg-purple-50 border border-purple-200 rounded-lg text-xs flex items-center gap-2"
                        >
                          <ToolIcon size={14} className="text-purple-600" />
                          <span className="text-purple-700 font-medium capitalize">
                            {toolCall.name?.replace(/_/g, ' ') || 'Tool'}
                          </span>
                          {toolCall.result && (
                            <span className="text-purple-600 ml-auto">✓ Executed</span>
                          )}
                          {toolCall.error && (
                            <span className="text-red-600 ml-auto">✗ Failed</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                
                {/* Message bubble */}
              <div
                className={`max-w-3xl rounded-lg px-4 py-2 ${
                    isUser
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                  {editingIndex === idx ? (
                    // Edit mode
                    <div className="space-y-2">
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        className="w-full p-2 border border-gray-300 rounded text-gray-800 bg-white resize-none"
                        rows={4}
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={handleSaveEdit}
                          className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition-colors flex items-center gap-1.5 text-sm"
                        >
                          <Check size={14} />
                          Save
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="px-3 py-1.5 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 transition-colors flex items-center gap-1.5 text-sm"
                        >
                          <XIcon size={14} />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                        {/* Show uploaded files in message */}
                        {msg.files && msg.files.length > 0 && (
                          <div className={`mt-2 pt-2 flex flex-wrap gap-2 ${
                            isUser ? 'border-t border-white/30' : 'border-t border-gray-300'
                          }`}>
                            {msg.files.map((file: any, fileIdx: number) => (
                              <div
                                key={fileIdx}
                                className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs ${
                                  isUser
                                    ? 'bg-white/20 text-white'
                                    : 'bg-gray-200 text-gray-700'
                                }`}
                              >
                                <FileText size={12} />
                                <span className="truncate max-w-[150px]">{file.name}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {/* Edit button */}
                        <button
                          onClick={() => handleStartEdit(idx)}
                          className={`p-1.5 rounded transition-colors ${
                            isUser
                              ? 'hover:bg-primary-700 text-white'
                              : 'hover:bg-gray-200 text-gray-600'
                          }`}
                          title="Edit message"
                        >
                          <Edit2 size={14} />
                        </button>
                        {/* TTS button for assistant messages */}
                        {!isUser && msg.content && (
                          <button
                            onClick={() => handleTTS(msg.content)}
                            className={`p-1.5 rounded transition-colors ${
                              isUser
                                ? 'hover:bg-primary-700 text-white'
                                : 'hover:bg-gray-200 text-gray-600'
                            }`}
                            title="Text to Speech"
                          >
                            <Volume2 size={14} />
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Regenerate button for last assistant message */}
                {!isUser && idx === messages.length - 1 && !loading && (
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      onClick={handleRegenerate}
                      className="px-3 py-1.5 text-xs bg-gray-200 hover:bg-gray-300 text-gray-700 rounded transition-colors flex items-center gap-1.5"
                      title="Regenerate response"
                    >
                      <RefreshCw size={12} />
                      Regenerate
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
        {loading && (
          <div className="flex flex-col items-start mb-4">
            <span className="text-xs font-medium mb-1 px-2 text-gray-600">
              {botName}
            </span>
            <div className="bg-gray-100 rounded-lg px-4 py-2 flex items-center gap-3">
              <p className="text-gray-500">Thinking...</p>
              <button
                onClick={handleStop}
                className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded transition-colors flex items-center gap-1.5 text-sm"
                title="Stop generation"
              >
                <Square size={12} />
                Stop
              </button>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 p-4 bg-white">
        {/* Uploaded Files Preview */}
        {uploadedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {uploadedFiles.map((file, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-sm"
              >
                <FileText size={14} className="text-blue-600" />
                <span className="text-blue-700 truncate max-w-[200px]">{file.name}</span>
                <button
                  onClick={() => handleRemoveFile(idx)}
                  className="p-0.5 hover:bg-blue-200 rounded transition-colors"
                  title="Remove file"
                >
                  <X size={14} className="text-blue-600" />
                </button>
              </div>
            ))}
          </div>
        )}
        
        <div className="flex gap-2 items-end">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Type your message..."
              rows={1}
              className="input resize-none pr-32"
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-2">
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => handleFileUpload(e.target.files)}
                multiple
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 rounded-lg bg-gray-200 hover:bg-gray-300 text-gray-700 transition-colors"
                title="Upload File"
              >
                <Paperclip size={20} />
              </button>
              {recording && audioStream && (
                <div className="w-24 h-8 bg-gray-100 rounded-lg overflow-hidden border border-gray-200">
                  <AudioVisualizer stream={audioStream} />
                </div>
              )}
              <button
                onClick={handleSTT}
                className={`p-2 rounded-lg transition-colors ${
                  recording
                    ? 'bg-red-500 text-white'
                    : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                }`}
                title="Speech to Text"
              >
                <Mic size={20} />
              </button>
            </div>
          </div>
          {loading ? (
            <button
              onClick={handleStop}
              className="btn-primary bg-red-500 hover:bg-red-600"
            >
              <Square size={20} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() && uploadedFiles.length === 0}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send size={20} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
