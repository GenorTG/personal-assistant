'use client';

import { useState } from 'react';
import { Mic, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import { useServiceStatus } from '@/contexts/ServiceStatusContext';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { cn } from '@/lib/utils';

export default function STTSettings() {
  const { statuses, refresh } = useServiceStatus();
  const [selectedLanguage, setSelectedLanguage] = useState<string>('en');

  const sttStatus = statuses?.stt;
  const isReady = sttStatus?.status === 'ready';
  const isOffline = sttStatus?.status === 'offline';

  const getStatusIcon = () => {
    if (isOffline) return <XCircle size={16} className="text-destructive" />;
    if (isReady) return <CheckCircle size={16} className="text-green-500" />;
    return <XCircle size={16} className="text-yellow-500" />;
  };

  const getStatusVariant = (): 'default' | 'secondary' | 'destructive' | 'outline' => {
    if (isOffline) return 'destructive';
    if (isReady) return 'default';
    return 'secondary';
  };

  const getStatusText = () => {
    if (isOffline) return 'Service Offline';
    if (isReady) return 'Ready';
    return 'Not Initialized';
  };

  return (
    <div>
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Mic size={20} />
        Speech-to-Text Settings
      </h3>
      <div className="space-y-4">
        <Card>
          <CardContent className="p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {getStatusIcon()}
                <span className="font-medium">Status</span>
              </div>
              <Badge variant={getStatusVariant()}>{getStatusText()}</Badge>
            </div>

            <div className="text-sm text-muted-foreground space-y-1">
              <div>
                <span className="font-medium">Provider:</span> Whisper
              </div>
              <div className={cn("hidden", sttStatus?.response_time_ms && "block")}>
                <span className="font-medium">Response Time:</span> {sttStatus?.response_time_ms}ms
              </div>
            </div>
          </CardContent>
        </Card>

        <Alert variant="destructive" className={cn("hidden", isOffline && "block")}>
          <AlertDescription>
            <p className="text-sm mb-3">
              STT Service is unreachable. Please ensure the Whisper service is running.
            </p>
            <Button onClick={refresh} variant="destructive" className="w-full flex items-center justify-center gap-2">
              <RefreshCw size={16} />
              Retry Connection
            </Button>
          </AlertDescription>
        </Alert>

        <div>
          <Label className="block text-sm font-medium mb-1">Language</Label>
          <Select value={selectedLanguage} onValueChange={setSelectedLanguage} disabled={!isReady}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh', 'ko', 'ar', 'hi'].map((lang) => (
                <SelectItem key={lang} value={lang}>
                  {lang.toUpperCase()} - {getLanguageName(lang)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground mt-1">Language for speech recognition</p>
        </div>

        <Alert className={cn("hidden", isReady && "block")}>
          <AlertDescription>
            <strong>Ready to use!</strong> The STT service is initialized and ready to transcribe audio.
          </AlertDescription>
        </Alert>
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
