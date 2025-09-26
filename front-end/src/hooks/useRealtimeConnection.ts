import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:8000';

interface TranscriptionData {
  transcription: string;
  is_final: boolean;
}

interface AiResponseChunk {
  chunk: string;
}

// A union type for conversation entries
export type ConversationEntry = {
  speaker: 'user' | 'ai';
  text: string;
  is_final?: boolean; // is_final is only for user
};

export const useRealtimeConnection = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);

  useEffect(() => {
    const socket: Socket = io(SOCKET_URL, {
      transports: ['websocket'],
      path: '/socket.io',
    });

    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));

    socket.on('transcription_update', (data: TranscriptionData) => {
      setConversation(prev => {
        const lastEntry = prev[prev.length - 1];
        // If last entry was a non-final user utterance, replace it
        if (lastEntry && lastEntry.speaker === 'user' && !lastEntry.is_final) {
          const newConversation = [...prev.slice(0, -1)];
          newConversation.push({ speaker: 'user', text: data.transcription, is_final: data.is_final });
          return newConversation;
        } else {
          // Otherwise, add a new entry
          return [...prev, { speaker: 'user', text: data.transcription, is_final: data.is_final }];
        }
      });
    });

    socket.on('ai_response_chunk', (data: AiResponseChunk) => {
      setConversation(prev => {
        const lastEntry = prev[prev.length - 1];
        // If last entry was from AI, append to it
        if (lastEntry && lastEntry.speaker === 'ai') {
          const newConversation = [...prev.slice(0, -1)];
          newConversation.push({ speaker: 'ai', text: lastEntry.text + data.chunk });
          return newConversation;
        } else {
          // Otherwise, add a new AI entry
          return [...prev, { speaker: 'ai', text: data.chunk }];
        }
      });
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  return { isConnected, conversation };
};
