import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchAlerts, markAlertRead, markAllAlertsRead } from '../api/client';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './AlertBell.module.css';

export default function AlertBell({ lang }: { lang: Lang }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => fetchAlerts(false),
    refetchInterval: 30_000,
  });

  const unread = data?.unread_count ?? 0;
  const items = data?.items ?? [];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  async function onItem(alertId: number, requestId: number, readAt: string | null) {
    if (!readAt) {
      await markAlertRead(alertId);
      qc.invalidateQueries({ queryKey: ['alerts'] });
    }
    setOpen(false);
    navigate(`/triage?request_id=${requestId}`);
  }

  async function onMarkAll() {
    await markAllAlertsRead();
    qc.invalidateQueries({ queryKey: ['alerts'] });
  }

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.btn}
        data-testid="alert-bell"
        aria-label={t(lang, 'Alertes', 'Alerts')}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 7H3s3 0 3-7" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        </svg>
        {unread > 0 && (
          <span className={styles.badge} data-testid="alert-badge">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className={styles.panel} data-testid="alert-panel" role="dialog">
          <div className={styles.panelHeader}>
            <span>{t(lang, 'Alertes', 'Alerts')}</span>
            {unread > 0 && (
              <button type="button" className={styles.markAll} onClick={onMarkAll}>
                {t(lang, 'Tout lu', 'Mark all read')}
              </button>
            )}
          </div>
          {items.length === 0 && (
            <p className={styles.empty}>{t(lang, 'Aucune alerte', 'No alerts')}</p>
          )}
          {items.map((a) => (
            <button
              key={a.alert_id}
              type="button"
              className={`${styles.item} ${a.read_at ? '' : styles.itemUnread}`}
              onClick={() => onItem(a.alert_id, a.request_id, a.read_at)}
            >
              <p className={styles.summary}>{a.summary}</p>
              <p className={styles.meta}>
                #{a.request_id}
                {a.raw_title ? ` · ${a.raw_title}` : ''}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
