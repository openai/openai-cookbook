import { useEffect, useId, useRef, useState } from 'react';
import { ImageUp, LoaderCircle, Sparkles, X } from 'lucide-react';
import { api, ApiError } from './api';
import SpaceIcon from './SpaceIcon';
import type { SpaceIcon as SpaceIconData } from './types';

type Props = {
  spaceId: string;
  icon?: SpaceIconData;
  hasBuilt: boolean;
  onClose: () => void;
  onChanged: (icon: SpaceIconData) => void;
  onExpired: () => void;
};
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Could not read that image. Try another file.'));
    reader.onerror = () => reject(new Error('Could not read that image. Try another file.'));
    reader.readAsDataURL(file);
  });
}

export default function SpaceIconEditor({ spaceId, icon, hasBuilt, onClose, onChanged, onExpired }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const helpId = useId();
  const [currentIcon, setCurrentIcon] = useState(icon);
  const [pending, setPending] = useState<'upload' | 'generate' | null>(null);
  const [error, setError] = useState(icon?.status === 'error' ? icon.error || 'Could not create an icon. Please try again.' : '');
  const [saved, setSaved] = useState(false);
  const callbacks = useRef({ onChanged, onExpired });
  callbacks.current = { onChanged, onExpired };
  const active = useRef(true);
  const mutation = useRef(false);
  const requestVersion = useRef(0);
  const base = `/api/spaces/${encodeURIComponent(spaceId)}/icon`;
  const generating = currentIcon?.status === 'generating' || pending === 'generate';

  useEffect(() => {
    active.current = true;
    const element = dialog.current;
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => {
      active.current = false;
      element?.close();
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    setCurrentIcon(icon);
    if (icon?.status === 'error') setError(icon.error || 'Could not create an icon. Please try again.');
  }, [icon]);
  useEffect(() => {
    if (currentIcon?.status !== 'generating') return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const version = requestVersion.current;
      try {
        const result = await api<{ icon: SpaceIconData }>(base);
        if (cancelled || mutation.current || version !== requestVersion.current) return;
        setCurrentIcon(result.icon);
        callbacks.current.onChanged(result.icon);
        if (result.icon.status === 'error') setError(result.icon.error || 'Could not create an icon. Please try again.');
        else if (result.icon.status === 'ready') { setError(''); setSaved(true); }
      } catch (failure) {
        if (cancelled || version !== requestVersion.current) return;
        if (failure instanceof ApiError && failure.status === 401) callbacks.current.onExpired();
        else setError('Reconnecting to your icon. You can close this window while it finishes.');
      } finally {
        if (!cancelled) timer = setTimeout(() => void poll(), 2000);
      }
    }
    timer = setTimeout(() => void poll(), 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [base, currentIcon?.status]);

  function reportFailure(failure: unknown) {
    if (failure instanceof ApiError && failure.status === 401) callbacks.current.onExpired();
    if (active.current) setError(failure instanceof Error ? failure.message : 'Could not update your icon. Please try again.');
  }
  async function upload(file?: File) {
    if (!file || mutation.current) return;
    setError(''); setSaved(false);
    if (!IMAGE_TYPES.has(file.type)) { setError('Choose a PNG, JPG or WebP image.'); return; }
    if (!file.size || file.size > MAX_UPLOAD_BYTES) { setError('Choose an image smaller than 5 MB.'); return; }
    mutation.current = true; ++requestVersion.current; setPending('upload');
    try {
      const dataUrl = await readImage(file);
      const result = await api<{ icon: SpaceIconData }>(base, { dataUrl });
      callbacks.current.onChanged(result.icon);
      if (active.current) { setCurrentIcon(result.icon); setSaved(true); }
    } catch (failure) { reportFailure(failure); }
    finally { mutation.current = false; if (active.current) setPending(null); }
  }
  async function generate() {
    if (mutation.current || generating || !hasBuilt) return;
    mutation.current = true; ++requestVersion.current; setPending('generate'); setError(''); setSaved(false);
    try {
      const result = await api<{ icon: SpaceIconData }>(`${base}/generate`, {});
      callbacks.current.onChanged(result.icon);
      if (active.current) setCurrentIcon(result.icon);
    } catch (failure) { reportFailure(failure); }
    finally { mutation.current = false; if (active.current) setPending(null); }
  }

  return <dialog ref={dialog} className="space-icon-dialog" aria-labelledby={titleId} aria-describedby={helpId} onClose={event => {
    // StrictMode closes and reopens this same element while replaying effects.
    // Its queued close event must not dismiss a dialog that is open again.
    if (active.current && !event.currentTarget.open) onClose();
  }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <button className="space-icon-dialog-close" onClick={onClose} aria-label="Close space icon settings"><X size={19}/></button>
    <div className="space-icon-editor-preview"><SpaceIcon icon={currentIcon} size={132}/></div>
    <h2 id={titleId}>Your space icon</h2>
    <p id={helpId}>A little picture of your world.</p>
    <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label="Choose a space icon image" onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; void upload(file); }}/>
    <div className="space-icon-editor-actions">
      <button className="space-icon-upload" data-voice-manual aria-description="Tap Upload image to choose a file from your device." disabled={pending !== null} onClick={() => fileInput.current?.click()}>{pending === 'upload' ? <LoaderCircle size={17} className="spin"/> : <ImageUp size={17}/>}<span>{pending === 'upload' ? 'Uploading…' : 'Upload image'}</span></button>
      <button className="space-icon-generate" disabled={pending !== null || generating || !hasBuilt} onClick={() => void generate()}>{generating ? <LoaderCircle size={16} className="spin"/> : <Sparkles size={16}/>}<span>{generating ? 'Creating your icon…' : 'Generate a new icon'}</span></button>
    </div>
    <span className="space-icon-file-hint">PNG, JPG or WebP · up to 5 MB</span>
    <div className="space-icon-editor-status" aria-live="polite">{error ? <p className="space-icon-editor-error" role="alert">{error}</p> : generating ? <p>You can keep exploring while it takes shape.</p> : saved ? <p>Saved. Your icon is updated everywhere.</p> : !hasBuilt ? <p>Build your space to generate its icon, or upload one now.</p> : null}</div>
  </dialog>;
}
