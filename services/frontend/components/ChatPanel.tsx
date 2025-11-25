'use client';

import { useState, useEffect, useRef } from 'react';
import { Send, Mic, Volume2 } from 'lucide-react';
import { api } from '@/lib/api';
import AudioVisualizer from './AudioVisualizer';

interface ChatPanelProps {
  conversationId: string | null;
}

export default function ChatPanel({ conversationId }: ChatPanelProps) {
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [userName, setUserName] = useState<string>('You');
  const [botName, setBotName] = useState<string>('Assistant');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    loadUserNames();
  }, []);

  useEffect(() => {
    if (conversationId) {
      loadConversation();
    } else {
      setMessages([]);
    }
  }, [conversationId]);

  const loadUserNames = async () => {
    try {
      // Wait for backend to be ready first
      const ready = await api.checkBackendHealth();
      if (!ready) {
        // Backend not ready yet, will retry later
        return;
      }
      const data = await api.getSettings() as any;
      if (data.settings?.user_profile?.name) {
        setUserName(data.settings.user_profile.name);
      }
      if (data.settings?.character_card?.name) {
        setBotName(data.settings.character_card.name);
      }
    } catch (error) {
      // Only log if it's not a "backend not ready" error
      if (error instanceof Error && !error.message.includes('Backend is not responding')) {
        console.error('Error loading user names:', error);
      }
    }
  };

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
    } catch (error) {
      console.error('Error loading conversation:', error);
      // If conversation doesn't exist, clear messages
      setMessages([]);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    // Add user message immediately
    const newUserMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, newUserMessage]);

    try {
      const response = await api.sendMessage(userMessage, conversationId || undefined) as any;
      
      // Update conversation ID if new
      if (response.conversation_id && response.conversation_id !== conversationId) {
        window.location.reload(); // Reload to update conversation list
      }

      // Add assistant response
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      alert(`Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
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
                {/* Message bubble */}
              <div
                className={`max-w-3xl rounded-lg px-4 py-2 ${
                    isUser
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                  <div className="flex items-start justify-between gap-2">
                    <p className="whitespace-pre-wrap flex-1">{msg.content}</p>
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
                        <Volume2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
        {loading && (
          <div className="flex flex-col items-start mb-4">
            <span className="text-xs font-medium mb-1 px-2 text-gray-600">
              {botName}
            </span>
            <div className="bg-gray-100 rounded-lg px-4 py-2">
              <p className="text-gray-500">Thinking...</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 p-4">
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
              className="input resize-none pr-12"
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-2">
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
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
