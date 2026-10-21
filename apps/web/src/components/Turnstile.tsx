import { useEffect, useRef } from 'react';

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opts: {
          sitekey: string;
          action?: string;
          callback?: (token: string) => void;
          'expired-callback'?: () => void;
          'error-callback'?: () => void;
          theme?: 'light' | 'dark' | 'auto';
        },
      ) => string;
      remove: (widgetId?: string) => void;
    };
    onTurnstileApiLoad?: () => void;
  }
}

const SCRIPT_ID = 'cf-turnstile-api';
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;

let scriptPromise: Promise<void> | null = null;

function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      if (window.turnstile) resolve();
      else {
        existing.addEventListener('load', () => resolve());
        existing.addEventListener('error', () => reject(new Error('Turnstile script failed')));
      }
      return;
    }
    window.onTurnstileApiLoad = () => resolve();
    const s = document.createElement('script');
    s.id = SCRIPT_ID;
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onTurnstileApiLoad';
    s.async = true;
    s.onerror = () => reject(new Error('Turnstile script failed'));
    document.head.appendChild(s);
  });
  return scriptPromise;
}

type Props = {
  action: string;
  onToken: (token: string | null) => void;
  resetKey?: number;
};

export default function Turnstile({ action, onToken, resetKey = 0 }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;

  useEffect(() => {
    if (!SITE_KEY || !hostRef.current) {
      onTokenRef.current(null);
      return;
    }
    let cancelled = false;

    loadTurnstileScript()
      .then(() => {
        if (cancelled || !hostRef.current || !window.turnstile) return;
        if (widgetIdRef.current) {
          window.turnstile.remove(widgetIdRef.current);
          widgetIdRef.current = null;
        }
        hostRef.current.innerHTML = '';
        widgetIdRef.current = window.turnstile.render(hostRef.current, {
          sitekey: SITE_KEY,
          action,
          callback: (token) => onTokenRef.current(token),
          'expired-callback': () => onTokenRef.current(null),
          'error-callback': () => onTokenRef.current(null),
          theme: 'light',
        });
      })
      .catch(() => onTokenRef.current(null));

    return () => {
      cancelled = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [action, resetKey]);

  if (!SITE_KEY) {
    return (
      <p data-testid="turnstile-missing" style={{ color: 'crimson', fontSize: '0.85rem' }}>
        Turnstile site key missing (VITE_TURNSTILE_SITE_KEY).
      </p>
    );
  }

  return <div ref={hostRef} data-testid={`turnstile-${action}`} />;
}
