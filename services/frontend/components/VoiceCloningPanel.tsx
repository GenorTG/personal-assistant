'use client';

import { useState, useRef, useEffect } from 'react';
import { Upload, Mic, Play, Square, Trash2, Loader } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface VoiceCloningPanelProps {
  backendName: string;
  onVoiceUploaded?: () => void;
}

export default function VoiceCloningPanel({
  backendName,
  onVoiceUploaded,
}: VoiceCloningPanelProps) {
  const { showError, showSuccess } = useToast();
  const [recording, setRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [customVoices, setCustomVoices] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const [voiceName, setVoiceName] = useState('');
  const [loading, setLoading] = useState(true);
  const [pendingDeleteVoice, setPendingDeleteVoice] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    loadCustomVoices();
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [backendName]);

  const loadCustomVoices = async () => {
    try {
      setLoading(true);
      const data = (await api.getCustomVoices(backendName)) as any;
      setCustomVoices(data.voices || []);
    } catch (error) {
      console.error('Error loading custom voices:', error);
    } finally {
      setLoading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        setRecordedAudio(audioBlob);
        const url = URL.createObjectURL(audioBlob);
        setAudioUrl(url);

        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setRecording(true);
    } catch (error) {
      console.error('Error starting recording:', error);
      showError('Failed to start recording. Please check microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  };

  const playRecordedAudio = () => {
    if (audioUrl && audioPlayerRef.current) {
      audioPlayerRef.current.play();
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!file) return;

    const allowedTypes = ['.wav', '.mp3', '.flac', '.m4a', '.ogg'];
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowedTypes.includes(fileExt)) {
      showError(`Unsupported file type. Allowed: ${allowedTypes.join(', ')}`);
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      showError('File size exceeds 10MB limit');
      return;
    }

    const name = voiceName || file.name.replace(/\.[^/.]+$/, '');
    if (!name) {
      showError('Please enter a voice name');
      return;
    }

    try {
      setUploading(true);
      await api.uploadVoiceToBackend(backendName, file, name);
      showSuccess(`Voice '${name}' uploaded successfully!`);
      setVoiceName('');
      await loadCustomVoices();
      onVoiceUploaded?.();
    } catch (error: any) {
      console.error('Error uploading voice:', error);
      showError(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleRecordedUpload = async () => {
    if (!recordedAudio) {
      showError('No recorded audio available');
      return;
    }

    const name = voiceName || `recorded_${Date.now()}`;
    if (!name) {
      showError('Please enter a voice name');
      return;
    }

    const audioFile = new File([recordedAudio], `${name}.wav`, {
      type: 'audio/wav',
    });

    await handleFileUpload(audioFile);

    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioUrl(null);
    setRecordedAudio(null);
  };

  const handleDeleteVoice = async (voiceName: string) => {
    if (pendingDeleteVoice === voiceName) {
      // Second click - confirm delete
      try {
        setUploading(true);
        await api.deleteCustomVoice(backendName, voiceName);
        showSuccess('Voice deleted successfully');
        await loadCustomVoices();
        setPendingDeleteVoice(null);
      } catch (error: any) {
        console.error('Error deleting voice:', error);
        showError(`Failed to delete: ${error.message}`);
      } finally {
        setUploading(false);
      }
    } else {
      // First click - show confirmation state
      setPendingDeleteVoice(voiceName);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteVoice(null), 3000);
    }
  };

  const hasRecordedAudio = recordedAudio && audioUrl;
  const hasVoices = customVoices.length > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Voice Cloning</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs font-medium mb-1">Voice Name</Label>
            <Input
              type="text"
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              placeholder="Enter a name for this voice"
              className="w-full text-sm"
              maxLength={50}
            />
          </div>

          <div>
            <Label className="text-xs font-medium mb-1">Upload Audio File</Label>
            <div className="flex items-center gap-2">
              <Label className="flex-1 cursor-pointer">
                <Input
                  type="file"
                  accept=".wav,.mp3,.flac,.m4a,.ogg"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      handleFileUpload(file);
                      e.target.value = '';
                    }
                  }}
                  className="hidden"
                  disabled={uploading}
                />
                <Button variant="outline" className="w-full flex items-center gap-2" asChild>
                  <span>
                    <Upload size={16} />
                    Choose File
                  </span>
                </Button>
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              WAV, MP3, FLAC, M4A, or OGG (~30 seconds recommended)
            </p>
          </div>

          <div>
            <Label className="text-xs font-medium mb-1">Record Audio</Label>
            <div className="flex items-center gap-2">
              <Button
                onClick={startRecording}
                disabled={uploading || recording}
                variant="default"
                size="sm"
                className={cn("hidden flex items-center gap-2", !recording && "flex")}
              >
                <Mic size={16} />
                Start Recording
              </Button>
              <Button
                onClick={stopRecording}
                variant="destructive"
                size="sm"
                className={cn("hidden flex items-center gap-2", recording && "flex")}
              >
                <Square size={16} />
                Stop Recording
              </Button>

              <Button
                onClick={playRecordedAudio}
                variant="default"
                size="sm"
                className={cn("hidden flex items-center gap-2", hasRecordedAudio && "flex")}
              >
                <Play size={16} />
                Play
              </Button>
              <Button
                onClick={handleRecordedUpload}
                disabled={uploading || !voiceName}
                variant="secondary"
                size="sm"
                className={cn("hidden flex items-center gap-2", hasRecordedAudio && "flex")}
              >
                {uploading ? <Loader size={16} className="animate-spin" /> : <Upload size={16} />}
                Upload Recording
              </Button>
            </div>
            <p className={cn("hidden text-xs text-destructive mt-1 flex items-center gap-1", recording && "flex")}>
              <span className="w-2 h-2 bg-destructive rounded animate-pulse"></span>
              Recording...
            </p>
            <audio ref={audioPlayerRef} src={audioUrl || undefined} className="hidden" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Custom Voices</CardTitle>
            <Button onClick={loadCustomVoices} disabled={loading} variant="ghost" size="sm" className="text-xs">
              <span className={cn("hidden", loading && "block")}>Loading...</span>
              <span className={cn("hidden", !loading && "block")}>Refresh</span>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className={cn("hidden text-sm text-muted-foreground py-4 text-center", loading && "block")}>
            <Loader size={16} className="animate-spin inline-block mr-2" />
            Loading voices...
          </div>
          <div className={cn("hidden text-sm text-muted-foreground py-4 text-center", !loading && !hasVoices && "block")}>
            No custom voices uploaded yet
          </div>
          <ScrollArea className={cn("hidden max-h-60", !loading && hasVoices && "block")}>
            <div className="space-y-2">
              {customVoices.map((voice: any) => {
                if (!voice) return null;
                const voiceKey = voice.name || voice.filename || 'unknown';
                const voiceDisplayName = voice.name || voice.filename || 'Unknown';
                return (
                  <Card key={voiceKey} className="p-2">
                    <CardContent className="p-0">
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{voiceDisplayName}</p>
                          <div className={cn("hidden text-xs text-muted-foreground", voice.file_size && "block")}>
                            {(voice.file_size / 1024).toFixed(1)} KB
                            <span className={cn("hidden", voice.upload_date && "inline")}>
                              {' '}• {new Date(voice.upload_date).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                        <Button
                          onClick={() => handleDeleteVoice(voiceKey)}
                        disabled={uploading}
                        variant={pendingDeleteVoice === voiceKey ? "destructive" : "outline"}
                        size="sm"
                        className={cn(
                          "ml-2 text-xs flex items-center gap-1",
                          pendingDeleteVoice === voiceKey ? "bg-destructive text-destructive-foreground" : ""
                        )}
                        title={pendingDeleteVoice === voiceKey ? "Click again to confirm" : "Delete voice"}
                      >
                        {pendingDeleteVoice === voiceKey ? "Confirm" : (
                          <>
                            <Trash2 size={12} />
                            Delete
                          </>
                        )}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
                );
              })}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
