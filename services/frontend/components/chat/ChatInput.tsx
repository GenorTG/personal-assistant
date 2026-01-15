'use client';

import { useRef } from 'react';
import { Send, Mic, Paperclip, X, FileText, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import AudioVisualizer from '@/components/AudioVisualizer';

interface ChatInputProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  loading: boolean;
  recording: boolean;
  audioStream: MediaStream | null;
  uploadedFiles: File[];
  onFileUpload: (files: FileList | null) => void;
  onRemoveFile: (index: number) => void;
  disabled?: boolean;
  onSTT?: () => void;
}

export function ChatInput({
  input,
  onInputChange,
  onSend,
  onStop,
  loading,
  recording,
  audioStream,
  uploadedFiles,
  onFileUpload,
  onRemoveFile,
  disabled,
  onSTT,
}: ChatInputProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="border-t border-border p-4 bg-background">
      <div className={cn("hidden mb-2 flex flex-wrap gap-2", uploadedFiles.length > 0 && "flex")}>
        {uploadedFiles.map((file, idx) => (
          <div
            key={idx}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded text-sm"
          >
            <FileText size={14} className="text-blue-600" />
            <span className="text-blue-700 truncate max-w-[200px]">{file.name}</span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onRemoveFile(idx)}
              className="h-4 w-4 p-0 hover:bg-blue-200"
              title="Remove file"
            >
              <X size={14} className="text-blue-600" />
            </Button>
          </div>
        ))}
      </div>

      <div className="flex gap-2 items-end">
        <div className="flex-1 relative">
          <Textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            placeholder="Type your message..."
            rows={1}
            className="resize-none pr-32"
            disabled={disabled}
          />
          <div className="absolute right-2 bottom-2 flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => onFileUpload(e.target.files)}
              multiple
              className="hidden"
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              className="h-8 w-8"
              title="Upload File"
            >
              <Paperclip size={20} />
            </Button>
            <div className={cn("hidden", recording && audioStream && "block w-24 h-8 bg-muted rounded overflow-hidden border border-border")}>
              <AudioVisualizer stream={audioStream!} />
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onSTT}
              disabled={!onSTT || disabled}
              className={cn(
                "h-8 w-8",
                recording ? 'bg-destructive text-destructive-foreground' : ''
              )}
              title={recording ? "Stop Recording" : "Speech to Text"}
            >
              <Mic size={20} />
            </Button>
          </div>
        </div>
        <div className={cn("hidden", loading && "block")}>
          <Button onClick={onStop} variant="destructive" size="icon">
            <Square size={20} />
          </Button>
        </div>
        <div className={cn("hidden", !loading && "block")}>
          <Button
            onClick={onSend}
            disabled={(!input.trim() && uploadedFiles.length === 0) || disabled}
            size="icon"
          >
            <Send size={20} />
          </Button>
        </div>
      </div>
    </div>
  );
}

