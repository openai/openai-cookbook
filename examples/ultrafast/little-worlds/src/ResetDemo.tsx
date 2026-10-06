import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { LoaderCircle, RotateCcw } from 'lucide-react';
import { resetDemo } from './api';
import type { VoiceActionResult } from './live-voice';
import { registerVoiceAction } from './voice-action-registry';
import './reset-demo.css';

type ResetDemoProps = {
  onReset: () => void;
  dark?: boolean;
};

export default function ResetDemo({ onReset, dark = false }: ResetDemoProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const pendingRef = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  function open() {
    if (pendingRef.current || dialog.current?.open) return;
    setError(null);
    dialog.current?.showModal();
    cancelButton.current?.focus({ preventScroll: true });
  }

  function close() {
    if (!pendingRef.current) dialog.current?.close();
  }

  const confirm = useCallback(async (): Promise<VoiceActionResult> => {
    if (pendingRef.current) return { ok: false, message: 'The demo is already resetting. Please wait for it to finish.' };
    pendingRef.current = true;
    setPending(true);
    setError(null);
    try {
      await resetDemo();
    } catch (failure) {
      pendingRef.current = false;
      const message = failure instanceof Error ? failure.message : 'Could not reset the demo. Please try again.';
      if (mounted.current) {
        setPending(false);
        setError(message);
      }
      return { ok: false, message };
    }
    // Always complete the app reset even if revoking the current session has
    // already navigated away from the view that opened this dialog.
    if (mounted.current) dialog.current?.close();
    onReset();
    return { ok: true, message: 'The demo was reset. The original spaces and connections have been restored.' };
  }, [onReset]);

  useEffect(() => {
    if (confirmButton.current) return registerVoiceAction(confirmButton.current, confirm);
  }, [confirm]);

  return <>
    <button ref={trigger} type="button" className={`reset-demo-trigger${dark ? ' reset-demo-trigger-dark' : ''}`} onClick={open} aria-haspopup="dialog">
      <RotateCcw size={13} strokeWidth={1.5} aria-hidden="true"/><span>Reset demo</span>
    </button>
    <dialog ref={dialog} className="reset-demo-dialog" data-voice-confirmation aria-labelledby={titleId} aria-describedby={descriptionId} aria-busy={pending}
      onCancel={event => { if (pendingRef.current) event.preventDefault(); }}
      onClose={() => { if (!pendingRef.current) trigger.current?.focus({ preventScroll: true }); }}
      onKeyDown={event => event.stopPropagation()}
      onClick={event => {
        event.stopPropagation();
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close();
      }}>
      <div className="reset-demo-symbol" aria-hidden="true"><RotateCcw size={20} strokeWidth={1.3}/></div>
      <h2 id={titleId}>Back to the beginning?</h2>
      <p id={descriptionId}>Added accounts and their spaces will be removed. The original spaces and connections will be restored.</p>
      {error && <p className="reset-demo-error" role="alert">{error}</p>}
      <div className="reset-demo-actions">
        <button ref={cancelButton} type="button" className="reset-demo-cancel" onClick={close} disabled={pending} autoFocus>Cancel</button>
        <button ref={confirmButton} type="button" className="reset-demo-confirm" onClick={() => void confirm()} disabled={pending}>
          {pending && <LoaderCircle size={14} className="reset-demo-spinner" aria-hidden="true"/>}
          <span>{pending ? 'Resetting…' : 'Reset demo'}</span>
        </button>
      </div>
      <span className="reset-demo-status" role="status">{pending ? 'Restoring the original neighborhood.' : ''}</span>
    </dialog>
  </>;
}
