import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { searchPortfolio } from '../../api/client';
import type { PortfolioSearchResult } from '../../api/client';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { norm } from './format';
import { portfolioPath } from './shared';
import styles from './PortfolioSearch.module.css';

// One search box for the whole portfolio: units, buildings, projects, current
// tenants and building reference facts (fiche technique, paint specs). Every
// word must match, so "peinture 1234 maple" lands on that building's paint code.

type Hit = { key: string; href: string; primary: string; secondary?: string | null; tag?: string | null };
type Group = { id: string; label: string; hits: Hit[] };

const MIN_CHARS = 2;

/** ~120 characters of `text` around the first query word it contains. */
function snippet(text: string, q: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  if (flat.length <= 120) return flat;
  const hay = norm(flat);
  const at = norm(q).split(/[\s,;]+/).filter(Boolean)
    .map((w) => hay.indexOf(w)).filter((i) => i >= 0).sort((a, b) => a - b)[0] ?? 0;
  const start = Math.max(0, at - 40);
  return `${start > 0 ? '…' : ''}${flat.slice(start, start + 120)}${start + 120 < flat.length ? '…' : ''}`;
}

function groups(data: PortfolioSearchResult, lang: Lang, q: string): Group[] {
  const unit = (n: string | null, id: number) =>
    n ? t(lang, `Logement ${n}`, `Unit ${n}`) : t(lang, `Logement #${id}`, `Unit #${id}`);
  return [
    {
      id: 'facts',
      label: t(lang, 'Fiche technique', 'Building info'),
      hits: data.facts.map((f, i) => ({
        key: `f${i}`,
        href: `${portfolioPath.building(f.building_id)}#fiche-technique`,
        primary: `${f.label} : ${snippet(f.value, q)}`,
        secondary: f.building_adresse ?? f.web_building_name,
        tag: f.source === 'paint_spec' ? t(lang, 'Peinture', 'Paint') : null,
      })),
    },
    {
      id: 'units',
      label: t(lang, 'Logements', 'Units'),
      hits: data.units.map((u) => ({
        key: `u${u.unit_id}`,
        href: portfolioPath.unit(u.unit_id),
        primary: [unit(u.numero_appartement, u.unit_id), u.building_adresse].filter(Boolean).join(' — '),
        secondary: u.tenant_names.length
          ? u.tenant_names.join(', ')
          : t(lang, 'Vacant', 'Vacant'),
        tag: u.grandeur,
      })),
    },
    {
      id: 'tenants',
      label: t(lang, 'Locataires', 'Tenants'),
      hits: data.tenants.map((tn) => ({
        key: `t${tn.tenant_id}`,
        href: `${portfolioPath.unit(tn.unit_id)}?locataire=${tn.tenant_id}`,
        primary: tn.nom_complet ?? t(lang, 'Locataire sans nom', 'Unnamed tenant'),
        secondary: [unit(tn.numero_appartement, tn.unit_id), tn.building_adresse].filter(Boolean).join(' — '),
      })),
    },
    {
      id: 'buildings',
      label: t(lang, 'Bâtiments', 'Buildings'),
      hits: data.buildings.map((b) => ({
        key: `b${b.building_id}`,
        href: portfolioPath.building(b.building_id),
        primary: b.adresse ?? b.web_building_name ?? t(lang, `Bâtiment ${b.building_id}`, `Building ${b.building_id}`),
        secondary: [b.nom_unique_projet, b.ville, b.territoire].filter(Boolean).join(' · '),
      })),
    },
    {
      id: 'projects',
      label: t(lang, 'Projets', 'Projects'),
      hits: data.projects.map((p) => ({
        key: `p${p.project_id}`,
        href: portfolioPath.project(p.sector_id, p.project_id),
        primary: p.nom_unique_projet ?? t(lang, `Projet ${p.project_id}`, `Project ${p.project_id}`),
        secondary: [p.adresse_quickbooks, p.accounting_project_number && `No ${p.accounting_project_number}`]
          .filter(Boolean).join(' · '),
      })),
    },
  ].filter((g) => g.hits.length > 0);
}

export default function PortfolioSearch({ lang }: { lang: Lang }) {
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const id = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(id);
  }, [text]);

  // « / » focuses the search from anywhere on the page, like the board.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return;
      e.preventDefault();
      inputRef.current?.focus();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const enabled = q.length >= MIN_CHARS;
  const { data, isFetching, isError } = useQuery({
    queryKey: ['portfolio', 'search', q],
    queryFn: () => searchPortfolio(q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const grouped = useMemo(() => (data && enabled ? groups(data, lang, q) : []), [data, enabled, lang, q]);
  const flat = grouped.flatMap((g) => g.hits);
  useEffect(() => { setActive(0); }, [q]);

  const showList = open && text.trim().length >= MIN_CHARS;
  const go = (hit: Hit) => {
    setOpen(false);
    inputRef.current?.blur();
    navigate(hit.href);
  };

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      const hit = flat[active];
      if (hit) { e.preventDefault(); go(hit); }
    } else if (e.key === 'Escape') {
      if (open) { e.preventDefault(); setOpen(false); } else { setText(''); }
    }
  }

  const optionId = (i: number) => `${listId}-opt-${i}`;
  let index = -1;

  return (
    <div className={styles.box} ref={boxRef}>
      <svg className={styles.icon} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
           fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="9" cy="9" r="6" /><path d="M13.5 13.5L17 17" />
      </svg>
      <input
        ref={inputRef}
        type="search"
        className={styles.input}
        value={text}
        placeholder={t(lang, 'Adresse, logement, locataire…', 'Address, unit, tenant…')}
        title={t(lang, 'Adresse, logement, locataire, code de peinture…',
                       'Address, unit, tenant, paint code…')}
        aria-label={t(lang, 'Rechercher dans le portfolio', 'Search the portfolio')}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && flat[active] ? optionId(active) : undefined}
        data-testid="portfolio-global-search"
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      <kbd className={styles.kbd} aria-hidden="true">/</kbd>

      {showList && (
        <div className={styles.panel} data-testid="portfolio-search-results">
          {grouped.length > 0 ? (
            <ul id={listId} role="listbox" className={styles.list}
                aria-label={t(lang, 'Résultats', 'Results')}>
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
                          aria-selected={i === active}
                          className={`${styles.option} ${i === active ? styles.optionActive : ''}`}
                          onMouseEnter={() => setActive(i)}
                          onMouseDown={(e) => { e.preventDefault(); go(hit); }}
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
                : isFetching || !enabled || q !== text.trim()
                  ? t(lang, 'Recherche…', 'Searching…')
                  : t(lang, 'Aucun résultat. Essayez une adresse, un numéro de logement ou un nom.',
                             'No results. Try an address, unit number or name.')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
