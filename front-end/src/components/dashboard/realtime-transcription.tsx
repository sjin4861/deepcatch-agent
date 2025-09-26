'use client';

import { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Mic } from 'lucide-react';

type TranscriptionProps = {
  transcript: string;
};

export default function RealtimeTranscription({ transcript }: TranscriptionProps) {
  const [displayedTranscript, setDisplayedTranscript] = useState<{ speaker: string; text: string }[]>([]);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const lines = transcript ? transcript.split('\n') : [];

  useEffect(() => {
    if (!transcript) return;
    setDisplayedTranscript([]); // Reset on new transcript
    let currentIndex = 0;
    const interval = setInterval(() => {
      if (currentIndex < lines.length) {
        const line = lines[currentIndex];
        const [speaker, ...textParts] = line.split(': ');
        const text = textParts.join(': ');
        setDisplayedTranscript(prev => [...prev, { speaker, text }]);
        currentIndex++;
      } else {
        clearInterval(interval);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [transcript]);

  useEffect(() => {
    if (scrollAreaRef.current) {
        const viewport = scrollAreaRef.current.querySelector('div');
        if (viewport) {
            viewport.scrollTop = viewport.scrollHeight;
        }
    }
  }, [displayedTranscript]);

  return (
    <Card className="flex-1 flex flex-col min-h-[400px]">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Mic className="text-accent" />
          Live Transcription
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 pr-4 -mr-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {displayedTranscript.map((line, index) => (
              <div key={index} className="flex flex-col">
                <span className={`font-bold ${line.speaker === 'Agent' ? 'text-primary' : 'text-foreground'}`}>{line.speaker}</span>
                <p className="text-muted-foreground">{line.text}</p>
              </div>
            ))}
            {lines.length > 0 && displayedTranscript.length === 0 && (
                 <div className="flex items-center justify-center h-full text-muted-foreground">
                    <p>Waiting for transcription...</p>
                 </div>
            )}
            {lines.length === 0 && (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                    <p>No active call.</p>
                </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
