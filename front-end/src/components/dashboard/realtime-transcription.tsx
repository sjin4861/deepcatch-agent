'use client';

import { useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Mic, Bot } from 'lucide-react';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';

// Map speaker role to a display name and style
const speakerDetails = {
  user: {
    name: 'Caller',
    style: 'text-foreground',
  },
  ai: {
    name: 'Agent',
    style: 'text-primary',
  },
};

export default function RealtimeTranscription() {
  const { isConnected, conversation } = useRealtimeConnection();
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollAreaRef.current) {
        const viewport = scrollAreaRef.current.querySelector('div');
        if (viewport) {
            viewport.scrollTop = viewport.scrollHeight;
        }
    }
  }, [conversation]);

  const renderStatus = () => {
    if (!isConnected) {
      return "Connecting to real-time server...";
    }
    if (conversation.length === 0) {
      return "Waiting for call to start...";
    }
    return null;
  };

  const status = renderStatus();

  return (
    <Card className="flex-1 flex flex-col min-h-[400px]">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Mic className="text-accent" />
          Live Transcription
        </CardTitle>
        <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-sm text-muted-foreground">{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 pr-4 -mr-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {status ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <p>{status}</p>
              </div>
            ) : (
              conversation.map((entry, index) => (
                <div key={index} className="flex flex-col">
                  <span className={`font-bold ${speakerDetails[entry.speaker].style}`}>
                    {entry.speaker === 'ai' ? <Bot className="inline-block w-4 h-4 mr-2" /> : <Mic className="inline-block w-4 h-4 mr-2" />}
                    {speakerDetails[entry.speaker].name}
                  </span>
                  <p className="text-muted-foreground pl-6">{entry.text}</p>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
