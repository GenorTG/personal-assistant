'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useConversation } from '@/hooks/queries/useConversation';
import { useSendMessage, useRegenerateResponse, useUpdateMessage } from '@/hooks/mutations/useChatMutations';
import { useSamplerSettings } from '@/contexts/SamplerSettingsContext';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '@/contexts/ToastContext';
import { isNotFoundError } from '@/lib/utils';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import { parseTemplateVariables } from '@/lib/utils/templateParser';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import { QuickSettings } from './QuickSettings';

interface ChatPanelProps {
  conversationId: string | null;
  conversations?: any[];
  onConversationNotFound?: (conversationId: string) => void;
  onConversationCreated?: (conversationId: string) => void;
}

export default function ChatPanel({
  conversationId,
  conversations = [],
  onConversationNotFound,
  onConversationCreated,
}: ChatPanelProps) {
  const { settings: samplerSettings } = useSamplerSettings();
  const { userName: contextUserName, botName: contextBotName } = useSettings();
  const { showError } = useToast();
  const queryClient = useQueryClient();

  const [input, setInput] = useState('');
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editContent, setEditContent] = useState<string>('');
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [userName, setUserName] = useState<string>(contextUserName || 'You');
  const [botName, setBotName] = useState<string>(contextBotName || 'Assistant');
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [recording, setRecording] = useState(false);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const conversationExists = conversations.some(
    (c: any) => c.conversation_id === conversationId || c.id === conversationId
  );

  const { data: conversationData, error } = useConversation(
    conversationId,
    !!conversationId && conversationExists
  );

  // Handle case where conversation was deleted (404 error)
  useEffect(() => {
    if (error && isNotFoundError(error) && conversationId) {
      // Conversation not found, notify parent to switch to another one
      onConversationNotFound?.(conversationId);
    }
  }, [error, conversationId, onConversationNotFound]);

  // Combine regular messages with streaming content if active
  const messages = conversationData?.messages || [];
  // Parse template variables in messages for display (memoized)
  const displayMessages = useMemo(() => {
    const messagesToDisplay = isStreaming && streamingContent
      ? [...messages, { role: 'assistant', content: streamingContent, timestamp: new Date().toISOString() }]
      : messages;
    return messagesToDisplay.map(msg => ({
      ...msg,
      content: parseTemplateVariables(msg.content, userName, botName)
    }));
  }, [messages, isStreaming, streamingContent, userName, botName]);

  const sendMessage = useSendMessage();
  const regenerateResponse = useRegenerateResponse();
  const updateMessage = useUpdateMessage();

  const loading = sendMessage.isPending || regenerateResponse.isPending;

  useEffect(() => {
    if (contextUserName || contextBotName) {
      // Use setTimeout to defer setState and avoid synchronous setState in effect
      const timeoutId = setTimeout(() => {
        if (contextUserName) setUserName(contextUserName);
        if (contextBotName) setBotName(contextBotName);
      }, 0);
      return () => clearTimeout(timeoutId);
    }
    return undefined;
  }, [contextUserName, contextBotName]);

  useEffect(() => {
    if (conversationId && !conversationExists && onConversationNotFound) {
      onConversationNotFound(conversationId);
    }
    return undefined;
  }, [conversationId, conversationExists, onConversationNotFound]);

  // Cleanup audio stream on unmount
  useEffect(() => {
    return () => {
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioStream]);

  const handleFileUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const fileArray = Array.from(files);
    for (const file of fileArray) {
      try {
        await api.uploadFile(file);
        setUploadedFiles((prev) => [...prev, file]);
      } catch (error) {
        showError(`Error uploading ${file.name}: ${String(error)}`);
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [showError]);

  const handleRemoveFile = useCallback((index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleStop = useCallback(() => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
    }
    setIsStreaming(false);
    setStreamingContent('');
    
    // Remove any partial assistant response that was saved during streaming
    // Keep the user message intact so they can regenerate or send again
    if (conversationId) {
      const queryKey = queryKeys.conversations.detail(conversationId);
      
      // Optimistically remove any assistant messages after the last user message
      queryClient.setQueryData(queryKey, (old: any) => {
        if (!old || !old.messages || old.messages.length === 0) {
          return old;
        }
        
        // Find the last user message index
        let lastUserIndex = -1;
        for (let i = old.messages.length - 1; i >= 0; i--) {
          if (old.messages[i].role === 'user') {
            lastUserIndex = i;
            break;
          }
        }
        
        // If we found a user message, keep everything up to and including it
        // This removes any partial assistant response that was saved
        // IMPORTANT: Always preserve the last user message, even if it was optimistically added
        if (lastUserIndex >= 0) {
          return {
            ...old,
            messages: old.messages.slice(0, lastUserIndex + 1),
          };
        }
        
        // If no user message found but we have messages, keep all messages
        // (shouldn't happen, but be safe)
        return old;
      });
      
      // Don't invalidate immediately - this could cause the user message to be lost
      // if it was only optimistically added. Instead, let the backend handle cleanup
      // and only invalidate after a short delay to ensure backend has processed the abort
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey });
      }, 500);
    }
  }, [abortController, conversationId, queryClient]);

  const handleRegenerate = useCallback(async () => {
    if (!conversationId || loading) return;
    const controller = new AbortController();
    setAbortController(controller);
    await regenerateResponse.mutateAsync({
      conversationId,
      samplerSettings,
    });
  }, [conversationId, loading, regenerateResponse, samplerSettings]);

  const handleStartEdit = useCallback((index: number) => {
    setEditingIndex(index);
    setEditContent(messages[index].content);
  }, [messages]);

  const handleCancelEdit = useCallback(() => {
    setEditingIndex(null);
    setEditContent('');
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (editingIndex === null || !conversationId) {
      return;
    }
    
    if (!editContent.trim()) {
      return;
    }
    
    const message = messages[editingIndex];
    if (!message) {
      return;
    }
    
    // Prevent multiple simultaneous saves
    if (updateMessage.isPending) {
      return;
    }
    
    try {
      await updateMessage.mutateAsync({
        conversationId,
        messageIndex: editingIndex,
        content: editContent,
        role: message.role,
      });
      
      setEditingIndex(null);
      setEditContent('');
    } catch (error) {
      // Error is already handled by the mutation's onError callback
      // Don't clear edit state on error so user can retry
    }
  }, [editingIndex, conversationId, editContent, messages, updateMessage]);

  const handleSend = useCallback(async () => {
    if ((!input.trim() && uploadedFiles.length === 0) || loading) return;

    let userMessage = input.trim();
    if (uploadedFiles.length > 0) {
      const fileNames = uploadedFiles.map((f) => f.name).join(', ');
      userMessage = userMessage ? `${userMessage}\n\n[Files: ${fileNames}]` : `[Files: ${fileNames}]`;
    }

    setInput('');
    setUploadedFiles([]);
    setStreamingContent('');
    setIsStreaming(true);

    const controller = new AbortController();
    setAbortController(controller);

    try {
      let accumulatedContent = '';
      const response = await sendMessage.mutateAsync({
        message: userMessage,
        conversationId: conversationId || undefined,
        samplerSettings,
        abortController: controller,
        onStreamChunk: (chunk: string) => {
          accumulatedContent += chunk;
          setStreamingContent(accumulatedContent);
        },
      });

      setIsStreaming(false);
      setStreamingContent('');

      if (response?.conversation_id && response.conversation_id !== conversationId && onConversationCreated) {
        onConversationCreated(response.conversation_id);
      }
    } catch (error: any) {
      // Clear streaming state on error
      setIsStreaming(false);
      setStreamingContent('');
      setAbortController(null);
      
      // Don't show error for user-initiated aborts
      if (error.name === 'AbortError' || error.message?.includes('aborted')) {
        return;
      }
      
      // Extract error message and backend logs from response if available
      let errorMessage = 'Failed to send message';
      let backendLogs: any[] | null = null;
      
      if (error.message) {
        errorMessage = error.message;
      } else if (error.response) {
        if (error.response.detail) {
          errorMessage = error.response.detail;
        }
        if (error.response.logs && Array.isArray(error.response.logs)) {
          backendLogs = error.response.logs;
        }
      } else if (typeof error === 'string') {
        errorMessage = error;
      }
      
      // Add backend error logs to message if available
      if (backendLogs && backendLogs.length > 0) {
        const errorLogs = backendLogs.filter((log: any) => 
          log.level === 'ERROR' || log.level === 'CRITICAL'
        );
        if (errorLogs.length > 0) {
          errorMessage += `\n\nBackend errors:\n${errorLogs.slice(0, 2).map((log: any) => `[${log.level}] ${log.message}`).join('\n')}`;
          if (errorLogs.length > 2) {
            errorMessage += `\n... and ${errorLogs.length - 2} more error(s)`;
          }
        }
      }
      
      showError(`Error sending message: ${errorMessage}`);
    }
  }, [input, uploadedFiles, loading, conversationId, samplerSettings, sendMessage, onConversationCreated, showError]);

  const handleTTS = useCallback(async (content: string) => {
    try {
      const audioBlob = await api.textToSpeech(content);
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      await audio.play();
    } catch (error) {
      showError(`Error with text-to-speech: ${String(error)}`);
    }
  }, [showError]);

  const handleSTT = useCallback(async () => {
    if (recording) {
      // Stop recording
      try {
        if (mediaRecorderRef.current) {
          if (mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
          }
        }
        // Don't stop stream here - let onstop handler do cleanup
        setRecording(false);
      } catch (error: any) {
        showError(`Failed to stop recording: ${error.message || String(error)}`);
        // Force cleanup on error
        if (audioStream) {
          audioStream.getTracks().forEach(track => track.stop());
          setAudioStream(null);
        }
        setRecording(false);
      }
      return;
    }

    // Start recording
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setAudioStream(stream);
      setRecording(true);
      audioChunksRef.current = [];

      // Try to use webm with opus, fallback to default if not supported
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = 'audio/webm';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          mimeType = ''; // Use browser default
        }
      }

      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = (event: any) => {
        showError('Recording error occurred');
        setRecording(false);
        if (audioStream) {
          audioStream.getTracks().forEach(track => track.stop());
          setAudioStream(null);
        }
      };

      mediaRecorder.onstop = async () => {
        try {
          // Check if we have any audio data
          if (audioChunksRef.current.length === 0) {
            showError('No audio data recorded. Please try again.');
            return;
          }

          const audioBlob = new Blob(audioChunksRef.current, { 
            type: mimeType || 'audio/webm' 
          });

          // Validate blob size
          if (audioBlob.size === 0) {
            showError('Recorded audio is empty. Please try again.');
            return;
          }

          const response = await api.speechToText(audioBlob);
          
          if (response && response.text) {
            // Append transcribed text to input (or replace if empty)
            setInput(prev => prev ? `${prev} ${response.text}` : response.text);
          } else {
            showError('No transcription result received');
          }
        } catch (error: any) {
          showError(`Speech-to-text failed: ${error.message || String(error)}`);
        } finally {
          // Cleanup
          if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
            setAudioStream(null);
          }
          audioChunksRef.current = [];
        }
      };

      // Start recording with timeslice to ensure data is captured periodically
      // This ensures ondataavailable fires even if recording is short
      mediaRecorder.start(100); // Capture data every 100ms
    } catch (error: any) {
      showError(`Failed to start recording: ${error.message || String(error)}`);
      setRecording(false);
      setAudioStream(null);
    }
  }, [recording, audioStream, showError]);


  return (
    <div className="flex-1 flex flex-col bg-background min-h-0 h-full overflow-hidden">
      <div className="flex-1 min-h-0 overflow-hidden">
        <ChatMessages
          messages={displayMessages}
          userName={userName}
          botName={botName}
          editingIndex={editingIndex}
          editContent={editContent}
          onEditContentChange={setEditContent}
          onStartEdit={handleStartEdit}
          onSaveEdit={handleSaveEdit}
          onCancelEdit={handleCancelEdit}
          onRegenerate={handleRegenerate}
          onTTS={handleTTS}
          loading={loading || isStreaming}
          onStop={handleStop}
          isSaving={updateMessage.isPending}
        />
      </div>
      <QuickSettings />
      <ChatInput
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        onStop={handleStop}
        loading={loading}
        recording={recording}
        audioStream={audioStream}
        uploadedFiles={uploadedFiles}
        onFileUpload={handleFileUpload}
        onRemoveFile={handleRemoveFile}
        disabled={!conversationId}
        onSTT={handleSTT}
      />
    </div>
  );
}




