import React, { useRef, useEffect, useState, useCallback } from 'react';
import { RealtimeClient } from '@openai/realtime-api-beta';
import { Button } from '../components/button/Button';
import { Toggle } from '../components/toggle/Toggle';
import { french_instructions, spanish_instructions, tagalog_instructions, english_instructions, mandarin_instructions } from '../utils/translation_prompts.js';
import { WavRecorder } from '../lib/wavtools/index.js';
import './Styles.scss';
import { io, Socket } from 'socket.io-client';

export const OPENAI_API_KEY = process.env.REACT_APP_OPENAI_API_KEY;

export const DEFAULT_REALTIME_MODEL = "gpt-4o-realtime-preview-2024-12-17";
export const DEFAULT_REALTIME_VOICE = "coral";
interface RealtimeEvent {
  time: string;
  source: 'client' | 'server';
  event: any;
  count?: number;
}

// Define language codes and their corresponding instructions
const languageConfigs = [
  { code: 'fr', instructions: french_instructions },
  { code: 'es', instructions: spanish_instructions },
  { code: 'tl', instructions: tagalog_instructions },
  { code: 'en', instructions: english_instructions },
  { code: 'zh', instructions: mandarin_instructions },
];

// Map language codes to full names
const languageNames: Record<string, string> = {
  fr: 'French',
  es: 'Spanish',
  tl: 'Tagalog',
  en: 'English',
  zh: 'Mandarin',
};

// SpeakerPage component handles real-time audio recording and streaming for multiple languages
export function SpeakerPage() {
  const [realtimeEvents, setRealtimeEvents] = useState<RealtimeEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [canPushToTalk, setCanPushToTalk] = useState(true);
  const [transcripts, setTranscripts] = useState<{ transcript: string; language: string }[]>([]);
  const [showTranscripts, setShowTranscripts] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState(false);

  const wavRecorderRef = useRef<WavRecorder>(
    new WavRecorder({ sampleRate: 24000 })
  );

  const socketRef = useRef<Socket | null>(null);

  // Create a map of client references using the language codes
  const clientRefs = useRef(
    languageConfigs.reduce((acc, { code }) => {
      acc[code] = new RealtimeClient({
        apiKey: OPENAI_API_KEY,
        dangerouslyAllowAPIKeyInBrowser: true,
      });
      return acc;
    }, {} as Record<string, RealtimeClient>)
  ).current;

  // Update languageConfigs to include client references
  const updatedLanguageConfigs = languageConfigs.map(config => ({
    ...config,
    clientRef: { current: clientRefs[config.code] }
  }));

  // Function to connect to the conversation and set up real-time clients
  const connectConversation = useCallback(async () => {
    try {
      setIsLoading(true);
      const wavRecorder = wavRecorderRef.current;
      await wavRecorder.begin();
      await connectAndSetupClients();
      setIsConnected(true);
    } catch (error) {
      console.error('Error connecting to conversation:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Function to disconnect from the conversation and stop real-time clients
  const disconnectConversation = useCallback(async () => {
    try {
      setIsConnected(false);
      setIsRecording(false);
      const wavRecorder = wavRecorderRef.current;
      await disconnectClients();
      await wavRecorder.end();
    } catch (error) {
      console.error('Error disconnecting from conversation:', error);
    }
  }, []);

  // Function to connect and set up all clients
  const connectAndSetupClients = async () => {
    for (const { clientRef } of updatedLanguageConfigs) {
      const client = clientRef.current;
      await client.realtime.connect({ model: DEFAULT_REALTIME_MODEL });
      await client.updateSession({ voice: DEFAULT_REALTIME_VOICE });
    }
  };

  // Function to disconnect all clients
  const disconnectClients = async () => {
    for (const { clientRef } of updatedLanguageConfigs) {
      clientRef.current.disconnect();
    }
  };

  const startRecording = async () => {
    setIsRecording(true);
    const wavRecorder = wavRecorderRef.current;

    await wavRecorder.record((data) => {
      // Send mic PCM to all clients
      updatedLanguageConfigs.forEach(({ clientRef }) => {
        clientRef.current.appendInputAudio(data.mono);
      });
    });
  };

  const stopRecording = async () => {
    setIsRecording(false);
    const wavRecorder = wavRecorderRef.current;

    if (wavRecorder.getStatus() === 'recording') {
      await wavRecorder.pause();
    }

    // Create response for all clients
    updatedLanguageConfigs.forEach(({ clientRef }) => {
      clientRef.current.createResponse();
    });
  };

  const changeTurnEndType = async (value: string) => {
    const wavRecorder = wavRecorderRef.current;

    if (value === 'none') {
      // If 'none' is selected, pause the recorder and disable turn detection for all clients
      await wavRecorder.pause();
      updatedLanguageConfigs.forEach(({ clientRef }) => {
        clientRef.current.updateSession({ turn_detection: null });
      });
      // Allow manual push-to-talk
      setCanPushToTalk(true);
    } else {
      // If 'server_vad' is selected, enable server-based voice activity detection for all clients
      updatedLanguageConfigs.forEach(({ clientRef }) => {
        clientRef.current.updateSession({ turn_detection: { type: 'server_vad' } });
      });
      await wavRecorder.record((data) => {
        updatedLanguageConfigs.forEach(({ clientRef }) => {
          clientRef.current.appendInputAudio(data.mono);
        });
      });
      setCanPushToTalk(false);
    }
  };

  const toggleTranscriptsVisibility = () => {
    setShowTranscripts((prev) => !prev);
  };

  useEffect(() => {
    // Connect to mirror server
    socketRef.current = io('http://localhost:3001'); 
    return () => {
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  useEffect(() => {
    for (const { code, instructions, clientRef } of updatedLanguageConfigs) {
      const client = clientRef.current;
      client.updateSession({
        instructions,
        input_audio_transcription: { model: 'whisper-1' },
      });

      client.on('realtime.event', (ev: RealtimeEvent) => handleRealtimeEvent(ev, code));
      client.on('error', (err: any) => console.error(`${code} client error:`, err));

      client.on('conversation.updated', ({ delta }: any) => {
        console.log(`${code} client.on conversation.updated`, delta);
        if (delta?.audio && delta.audio.byteLength > 0) {
          console.log(`Emitting audio for ${code}:`, delta.audio);
          socketRef.current?.emit(`mirrorAudio:${code}`, delta.audio);
        }
      });
    }

    // Cleanup function to reset all clients when the component unmounts or dependencies change
    return () => {
      for (const { clientRef } of updatedLanguageConfigs) {
        clientRef.current.reset();
      }
    };
  }, [french_instructions, spanish_instructions, tagalog_instructions, english_instructions, mandarin_instructions]);

  const handleRealtimeEvent = (ev: RealtimeEvent, languageCode: string) => {
    // Check if the event type is a completed audio transcript
    if (ev.event.type == "response.audio_transcript.done") {
      console.log(ev.event.transcript);
      // Update the transcripts state by adding the new transcript with language code
      setTranscripts((prev) => [{ transcript: ev.event.transcript, language: languageCode }, ...prev]);
    }

    setRealtimeEvents((prev) => {
      const lastEvent = prev[prev.length - 1];
      if (lastEvent?.event.type === ev.event.type) {
        lastEvent.count = (lastEvent.count || 0) + 1;
        return [...prev.slice(0, -1), lastEvent];
      }
      return [...prev, ev];
    });
  };

  return (
    <div className="speaker-page">
      <h1>Speaker Page</h1>
      <div className="card">
        <div className="card-content">
          <p>Connect to send audio in French, Spanish, English, Mandarin, and Tagalog</p>
          <div className="tooltip-container">
            <button className="tooltip-trigger">Instructions</button>
            <div className="tooltip-content">
              <p><strong>Manual Mode:</strong> Click 'Start Recording' to begin translating your speech. Click 'Stop Recording' to end the translation.</p>
              <p><strong>VAD Mode:</strong> Voice Activity Detection automatically starts and stops recording based on your speech. No need to manually control the recording.</p>
            </div>
          </div>
        </div>
        <div className="toggle-container">
          {isConnected && (
            <Toggle
              defaultValue={false}
              labels={['Manual', 'VAD']}
              values={['none', 'server_vad']}
              onChange={(_, value) => changeTurnEndType(value)}
            />
          )}
        </div>
        <div className="card-footer">
          {isConnected ? (
            <Button label="Disconnect" onClick={disconnectConversation} />
          ) : (
            <Button
              label={isLoading ? 'Connecting...' : 'Connect'}
              onClick={connectConversation}
              disabled={isLoading}
            />
          )}
          {isConnected && canPushToTalk && (
            <Button
              label={isRecording ? 'Stop Recording' : 'Start Recording'}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={!isConnected}
            />
          )}
        </div>
      </div>
      <div className="transcript-list">
        <Button label={showTranscripts ? 'Hide Transcripts' : 'Show Transcripts'} onClick={toggleTranscriptsVisibility} />
        {showTranscripts && (
          <table>
            <tbody>
              {transcripts.map(({ transcript, language }, index) => (
                <tr key={index}>
                  <td>{languageNames[language]}</td>
                  <td>
                    <div className="transcript-box">{transcript}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}