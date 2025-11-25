'use client';

import { useState } from 'react';
import { Mic, CheckCircle, XCircle, Loader, RefreshCw, Download } from 'lucide-react';
import { api } from '@/lib/api';
import { useServiceStatus } from '@/contexts/ServiceStatusContext';

export default function STTSettings() {
  const { statuses, refresh } = useServiceStatus();
  const [initializing, setInitializing] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState<string>('en');

  const sttStatus = statuses?.stt;

  const handleInitialize = async () => {
    try {
      setInitializing(true);
      const result = await api.initializeSTT() as any;
      alert(`STT initialized successfully! Provider: ${result.provider}`);
      await refresh();
    } catch (error: any) {
      console.error('Error initializing STT:', error);
      alert(`Failed to initialize STT: ${error.message || 'Unknown error'}`);
    } finally {
      setInitializing(false);
    }
  };

  const getStatusIcon = () => {
    if (sttStatus?.status === 'offline') {
        return <XCircle size={16} className="text-red-500" />;
    }
    if (sttStatus?.status === 'ready') {
      return <CheckCircle size={16} className="text-green-500" />;
    }
    return <XCircle size={16} className="text-yellow-500" />;
  };

  const isReady = sttStatus?.status === 'ready';
  const isOffline = sttStatus?.status === 'offline';

  return (
    <div>
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Mic size={20} />
        Speech-to-Text Settings
      </h3>
      <div className="space-y-4">
        {/* Status */}
        <div className="p-3 border rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {getStatusIcon()}
              <span className="font-medium">Status</span>
            </div>
            <span className={`text-xs px-2 py-1 rounded ${
              isOffline
                ? 'bg-red-100 text-red-700'
                : isReady
                  ? 'bg-green-100 text-green-700' 
                  : 'bg-yellow-100 text-yellow-700'
            }`}>
              {isOffline ? 'Service Offline' : (isReady ? 'Ready' : 'Not Initialized')}
            </span>
          </div>
          
          <div className="text-sm text-gray-600 space-y-1">
            <div>
              <span className="font-medium">Provider:</span> Whisper
            </div>
            {sttStatus?.response_time_ms && (
              <div>
                <span className="font-medium">Response Time:</span> {sttStatus.response_time_ms}ms
              </div>
            )}
          </div>
        </div>

        {/* Offline/Retry Message */}
        {isOffline && (
          <div className="p-3 border rounded-lg bg-red-50 border-red-200">
            <p className="text-sm mb-3 text-red-800">
              STT Service is unreachable. Please ensure the Whisper service is running.
            </p>
            <button
              onClick={refresh}
              className="w-full flex items-center justify-center gap-2 btn-primary bg-red-600 hover:bg-red-700 border-red-600 text-white"
            >
              <RefreshCw size={16} />
              Retry Connection
            </button>
          </div>
        )}

        {/* Language Selection */}
        <div>
          <label className="block text-sm font-medium mb-1">Language</label>
          <select
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
            className="input w-full"
            disabled={!isReady}
          >
            {['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh', 'ko', 'ar', 'hi'].map((lang) => (
              <option key={lang} value={lang}>
                {lang.toUpperCase()} - {getLanguageName(lang)}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Language for speech recognition
          </p>
        </div>

        {/* Ready Info */}
        {isReady && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800">
              <strong>Ready to use!</strong> The STT service is initialized and ready to transcribe audio.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function getLanguageName(code: string): string {
  const names: Record<string, string> = {
    en: 'English',
    es: 'Spanish',
    fr: 'French',
    de: 'German',
    it: 'Italian',
    pt: 'Portuguese',
    ru: 'Russian',
    ja: 'Japanese',
    zh: 'Chinese',
    ko: 'Korean',
    ar: 'Arabic',
    hi: 'Hindi',
  };
  return names[code] || code;
}
