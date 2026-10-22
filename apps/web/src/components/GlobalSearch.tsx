import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { fetchRequests, searchPortfolio } from '../api/client';
import { t } from '../i18n';
import type { Lang } from '../i18n';
import { groups } from '../pages/Portfolio/PortfolioSearch';
import type { Group, Hit } from '../pages/Portfolio/PortfolioSearch';
import styles from './GlobalSearch.module.css';

// Search palette for the whole app. The sidebar holds a plain field; clicking
// it (or Ctrl/⌘+K) opens a centred palette that lists service calls plus
// everything the portfolio search covers (units, tenants, buildings, projects,
// paint codes and building facts).

const MIN_CHARS = 2;

async function searchAll(q: string, lang: Lang): Promise<Group[]> {
  const [requests, portfolio] = await Promise.all([
    // A failure in one source must not hide the other's results.
    fetchRequests({ q, limit: 6, sort_by: 'start_date', sort_dir: 'desc' }).catch(() => null),
    searchPortfolio(q, 5).catch(() => null),
  ]);
  if (!requests && !portfolio) throw new Error('search failed');
  const requestGroup: Group = {
    id: 'requests',
    label: t(lang, 'Appels de service', 'Service calls'),
    hits: (requests?.items ?? []).map((r) => ({
      key: `r${r.request_id}`,
      href: `/triage?request_id=${r.request_id}`,
      primary: r.raw_title ?? t(lang, `Appel #${r.request_id}`, `Call #${r.request_id}`),
      secondary: [r.asnu, r.building_address ?? r.building_name, r.start_date].filter(Boolean).join(' · '),
    })),
  };
  return [requestGroup, ...(portfolio ? groups(portfolio, lang, q) : [])].filter((g) => g.hits.length > 0);
}

function MagnifierIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="9" cy="9" r="6" /><path d="M13.5 13.5L17 17" />
    </svg>
  );
}

function Palette({ lang, onClose, onNavigate }: { lang: Lang; onClose: () => void; onNavigate?: () => void }) {
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);

  const trimmed = text.trim();
  const canSearch = trimmed.length >= MIN_CHARS;

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const id = setTimeout(() => setQ(trimmed), 250);
    return () => clearTimeout(id);
  }, [trimmed]);

  const enabled = q.length >= MIN_CHARS && q === trimmed;
  const { data, isFetching, isError } = useQuery({
    queryKey: ['global-search', q, lang],
    queryFn: () => searchAll(q, lang),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const grouped = useMemo(() => (data && q.length >= MIN_CHARS ? data : []), [data, q]);
  const flat = grouped.flatMap((g) => g.hits);
  useEffect(() => { setActive(0); }, [q]);
  const current = Math.min(active, Math.max(flat.length - 1, 0));

  const go = (hit: Hit) => {
    onClose();
    navigate(hit.href);
    onNavigate?.();
  };

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(Math.min(current + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(Math.max(current - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (flat[current]) go(flat[current]);
    }
  }

  const optionId = (i: number) => `${listId}-opt-${i}`;
  let index = -1;

  return createPortal(
    <div className={styles.scrim} onMouseDown={onClose} data-testid="global-search-scrim">
      <div className={styles.dialog} role="dialog" aria-modal="true"
           aria-label={t(lang, 'Recherche', 'Search')} onMouseDown={(e) => e.stopPropagation()}
           onKeyDown={(e) => {
             if (e.key !== 'Escape') return;
             e.preventDefault();
             onClose();
           }}>
        <div className={styles.head}>
          <MagnifierIcon className={styles.headIcon} />
          <input
            ref={inputRef}
            type="search"
            className={styles.headInput}
            value={text}
            placeholder={t(lang, 'Rechercher partout…', 'Search everything…')}
            aria-label={t(lang, "Rechercher dans toute l'application", 'Search the whole app')}
            role="combobox"
            aria-expanded={canSearch && flat.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={canSearch && flat.length > 0 ? optionId(current) : undefined}
            data-testid="global-search"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="button" className={styles.cancel} onClick={onClose}>
            {t(lang, 'Annuler', 'Cancel')}
          </button>
        </div>

        {!canSearch && (
          <p className={styles.status}>
            {t(lang, 'Adresse, logement, locataire, code de peinture…',
                     'Address, unit, tenant, paint code…')}
          </p>
        )}

        {canSearch && (
          <div className={styles.body} data-testid="global-search-results">
            {grouped.length > 0 ? (
              <ul id={listId} role="listbox" className={styles.list} aria-label={t(lang, 'Résultats', 'Results')}>
                {grouped.map((g) => (
                  <li key={g.id} role="presentation">
                    <p className={styles.groupLabel} role="presentation">{g.label}</p>
                    <ul role="group" aria-label={g.label} className={styles.groupList}>
                      {g.hits.map((hit) => {
                        index += 1;
                        const i = index;
                        return (
                          <li
                            key={hit.key}
                            id={optionId(i)}
                            role="option"
                            aria-selected={i === current}
                            className={`${styles.option} ${i === current ? styles.optionActive : ''}`}
                            onMouseEnter={() => setActive(i)}
                            onClick={() => go(hit)}
                          >
                            <span className={styles.primary}>{hit.primary}</span>
                            {(hit.secondary || hit.tag) && (
                              <span className={styles.secondary}>
                                {hit.tag && <span className={styles.tag}>{hit.tag}</span>}
                                {hit.secondary}
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.status} role="status">
                {isError
                  ? t(lang, 'La recherche a échoué. Réessayez.', 'Search failed. Try again.')
                  : isFetching || !enabled
                    ? t(lang, 'Recherche…', 'Searching…')
                    : t(lang, 'Aucun résultat.', 'No results.')}
              </p>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

export default function GlobalSearch({ lang, onNavigate }: { lang: Lang; onNavigate?: () => void }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() !== 'k' || !(e.ctrlKey || e.metaKey) || e.altKey) return;
      e.preventDefault();
      setOpen(true);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const close = () => {
    setOpen(false);
    // Put focus back on the sidebar field once the palette unmounts.
    setTimeout(() => triggerRef.current?.focus(), 0);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        aria-haspopup="dialog"
        aria-label={t(lang, "Rechercher dans toute l'application", 'Search the whole app')}
        data-testid="global-search-trigger"
        onClick={() => setOpen(true)}
      >
        <MagnifierIcon className={styles.triggerIcon} />
        {t(lang, 'Rechercher…', 'Search…')}
      </button>
      {open && <Palette lang={lang} onClose={close} onNavigate={onNavigate} />}
    </>
  );
}
