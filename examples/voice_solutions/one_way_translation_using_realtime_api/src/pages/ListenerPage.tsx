import React, { useRef, useState, useCallback, useEffect } from 'react';
import { io, Socket } from 'socket.io-client';
import { WavStreamPlayer } from '../lib/wavtools';
import { Button } from '../components/button/Button';
import './Styles.scss';

// ListenerPage component handles audio streaming for selected languages
export function ListenerPage() {
  const wavStreamPlayerRef = useRef(new WavStreamPlayer({ sampleRate: 24000 }));
  const socketRef = useRef<Socket | null>(null);

  // State variables for managing connection status and selected language
  const [isConnected, setIsConnected] = useState(false);
  const [selectedLang, setSelectedLang] = useState<'fr' | 'es' | 'tl' | 'en' | 'zh' | null>(null);

  // Centralize language data
  const languages = {
    fr: { name: 'French' },
    es: { name: 'Spanish' },
    tl: { name: 'Tagalog' },
    en: { name: 'English' },
    zh: { name: 'Mandarin' },
  } as const;

  type LanguageKey = keyof typeof languages;

  // Extract language options into a separate function
  const renderLanguageOptions = () => (
    Object.entries(languages).map(([key, { name }]) => (
      <option key={key} value={key}>{name}</option>
    ))
  );

  // Function to connect to the server and set up audio streaming
  const connectServer = useCallback(async () => {
    if (socketRef.current) return;
    try {
      const socket = io('http://localhost:3001');
      socketRef.current = socket;
      await wavStreamPlayerRef.current.connect();
      socket.on('connect', () => {
        console.log('Listener connected:', socket.id);
        setIsConnected(true);
      });
      socket.on('disconnect', () => {
        console.log('Listener disconnected');
        setIsConnected(false);
      });
    } catch (error) {
      console.error('Error connecting to server:', error);
    }
  }, []);

  // Function to disconnect from the server and stop audio streaming
  const disconnectServer = useCallback(async () => {
    console.log('Disconnect button clicked');
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }
    try {
      await wavStreamPlayerRef.current.interrupt();
      setIsConnected(false);
    } catch (error) {
      console.error('Error disconnecting from server:', error);
    }
  }, []);

  // Helper function to handle playing audio chunks
  const playAudioChunk = (lang: LanguageKey, chunk: ArrayBuffer) => {
    console.log(`Playing ${lang.toUpperCase()} chunk:`, chunk.byteLength);
    wavStreamPlayerRef.current.add16BitPCM(chunk);
  };

  // Dynamically create language handlers
  const languageHandlers: Record<LanguageKey, (chunk: ArrayBuffer) => void> = Object.keys(languages).reduce((handlers, lang) => {
    handlers[lang as LanguageKey] = (chunk) => playAudioChunk(lang as LanguageKey, chunk);
    return handlers;
  }, {} as Record<LanguageKey, (chunk: ArrayBuffer) => void>);

  // UseEffect to handle socket events for selected language
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !selectedLang) return;

    console.log(`Setting up listener for language: ${selectedLang}`);
    const handleChunk = languageHandlers[selectedLang];
    socket.on(`audioFrame:${selectedLang}`, handleChunk);

    return () => {
      console.log(`Cleaning up listener for language: ${selectedLang}`);
      socket.off(`audioFrame:${selectedLang}`, handleChunk);
    };
  }, [selectedLang]);

  return (
    <div className="listener-page">
      <h1>Listener Page</h1>
      <div className="card">
        <div className="card-content">
          <p>Select preferred language for translation</p>
          <div className="dropdown-container">
            <select
              value={selectedLang || ''}
              onChange={(e) => {
                const lang = e.target.value as LanguageKey;
                console.log(`Switching to ${languages[lang].name}`);
                setSelectedLang(lang);
              }}
            >
              <option value="" disabled>Select a language</option>
              {renderLanguageOptions()}
            </select>
          </div>
        </div>
        <div className="card-footer">
          {isConnected ? (
            <Button label="Disconnect" onClick={disconnectServer} />
          ) : (
            <Button label="Connect" onClick={connectServer} />
          )}
        </div>
      </div>
    </div>
  );
}