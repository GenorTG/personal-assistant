'use client';

import { useState } from 'react';
import { Mic, Volume2 } from 'lucide-react';
import { useServiceStatus } from '@/contexts/ServiceStatusContext';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import STTSettings from '../STTSettings';
import TTSSettings from '../TTSSettings';

export default function VoiceSettings() {
  const { statuses } = useServiceStatus();
  const [activeTab, setActiveTab] = useState<'stt' | 'tts'>('stt');

  // Get clean status indicators
  const sttStatus = statuses?.stt;
  const sttIsReady = sttStatus?.status === 'ready';
  const sttIsOffline = sttStatus?.status === 'offline';

  const ttsStatuses = statuses?.tts;
  const piperReady = ttsStatuses?.piper?.status === 'ready';
  const kokoroReady = ttsStatuses?.kokoro?.status === 'ready';
  const chatterboxReady = ttsStatuses?.chatterbox?.status === 'ready';
  const anyTTSReady = piperReady || kokoroReady || chatterboxReady;

  return (
    <div className="space-y-4">
      {/* Status Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* STT Status Card */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Mic size={18} className="text-muted-foreground" />
                <span className="font-medium text-sm">Speech-to-Text</span>
              </div>
              <Badge 
                variant={sttIsOffline ? 'destructive' : sttIsReady ? 'default' : 'secondary'}
                className="flex items-center gap-1"
              >
                {sttIsOffline ? (
                  <>
                    <XCircle size={12} />
                    Offline
                  </>
                ) : sttIsReady ? (
                  <>
                    <CheckCircle size={12} />
                    Ready
                  </>
                ) : (
                  'Unknown'
                )}
              </Badge>
            </div>
            {sttStatus?.response_time_ms && (
              <p className="text-xs text-muted-foreground">
                Response time: {sttStatus.response_time_ms}ms
              </p>
            )}
          </CardContent>
        </Card>

        {/* TTS Status Card */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Volume2 size={18} className="text-muted-foreground" />
                <span className="font-medium text-sm">Text-to-Speech</span>
              </div>
              <Badge 
                variant={anyTTSReady ? 'default' : 'secondary'}
                className="flex items-center gap-1"
              >
                {anyTTSReady ? (
                  <>
                    <CheckCircle size={12} />
                    Available
                  </>
                ) : (
                  <>
                    <XCircle size={12} />
                    Offline
                  </>
                )}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {piperReady && (
                <Badge variant="outline" className="text-xs">Piper</Badge>
              )}
              {kokoroReady && (
                <Badge variant="outline" className="text-xs">Kokoro</Badge>
              )}
              {chatterboxReady && (
                <Badge variant="outline" className="text-xs">Chatterbox</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('stt')}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-2",
            activeTab === 'stt'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          <Mic size={16} />
          Speech-to-Text
        </button>
        <button
          onClick={() => setActiveTab('tts')}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-2",
            activeTab === 'tts'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          <Volume2 size={16} />
          Text-to-Speech
        </button>
      </div>

      {/* Content */}
      <div>
        {activeTab === 'stt' && <STTSettings />}
        {activeTab === 'tts' && <TTSSettings />}
      </div>
    </div>
  );
}
