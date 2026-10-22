import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchTenantTurnover } from '../../api/client';
import type { PortfolioTenant, Turnover } from '../../api/client';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { fmtDate, fmtMoney, fmtTime } from './format';
import { MailIcon, PhoneIcon } from './icons';
import styles from './Portfolio.module.css';
import { formatPhone, telHref } from '../../lib/phone';

type Pair = readonly [string, string];

const MOVE_REASON: Record<string, Pair> = {
  lease_end: ['Fin de bail', 'Lease end'],
  lease_assignment: ['Cession de bail', 'Lease assignment'],
  eviction: ['Éviction', 'Eviction'],
};

const INTERCOM: Record<string, Pair> = {
  to_do: ['À faire', 'To do'],
  done: ['Fait', 'Done'],
  call_placed: ['Appel placé', 'Call placed'],
};

const APPLIANCE: Record<string, Pair> = {
  internet: ['Internet', 'Internet'],
  cuisiniere: ['Cuisinière', 'Stove'],
  refrigerateur: ['Réfrigérateur', 'Refrigerator'],
  'lave-vaisselle': ['Lave-vaisselle', 'Dishwasher'],
  laveuse: ['Laveuse', 'Washer'],
  secheuse: ['Sécheuse', 'Dryer'],
};

const CAPACITE: Record<string, Pair> = {
  named_on_lease: ['Signataire du bail', 'Named on lease'],
  took_over: ['Cessionnaire', 'Took over the lease'],
};

export function capaciteLabel(lang: Lang, v: string | null): string | null {
  if (!v) return null;
  const pair = CAPACITE[v];
  return pair ? pair[lang === 'fr' ? 0 : 1] : v;
}

function label(map: Record<string, Pair>, lang: Lang, v: string | null): string | null {
  if (!v) return null;
  const pair = map[v];
  return pair ? pair[lang === 'fr' ? 0 : 1] : v;
}

function yesNo(lang: Lang, v: boolean | null): string | null {
  if (v === null) return null;
  return v ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No');
}

/** Yes / No as a small pill, so a column of answers scans at a glance. */
function yesNoPill(lang: Lang, v: boolean | null): ReactNode {
  if (v === null) return null;
  return (
    <span className={`${styles.yn} ${v ? styles.ynYes : styles.ynNo}`}>
      {v ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No')}
    </span>
  );
}

/** A date with its time, on one line: "30 juin 2026 · 10:00". */
function when(date: string | null, time: string | null): string | null {
  const parts = [date, time].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

/** "current → new", or whichever side is known. */
function change(a: string | null, b: string | null): string | null {
  if (a && b) return a === b ? a : `${a} → ${b}`;
  return a ?? b;
}

type Fact = [string, ReactNode];

/** Definition list of the facts that have a value; nothing when all are empty. */
function Facts({ items, className }: { items: Fact[]; className?: string }) {
  const shown = items.filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (shown.length === 0) return null;
  return (
    <dl className={`${styles.facts} ${className ?? ''}`}>
      {shown.map(([k, v]) => (
        <div key={k} style={{ display: 'contents' }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function headlineDate(tv: Turnover): string | null {
  if (tv.tenant_role === 'outgoing') {
    return tv.move_out_confirmed_date ?? tv.lease_end_date ?? tv.assignment_desired_date;
  }
  return tv.move_in_confirmed_date ?? tv.lease_start_date
    ?? tv.move_out_confirmed_date ?? tv.lease_end_date ?? tv.assignment_desired_date;
}

function TurnoverCard({ tv, lang }: { tv: Turnover; lang: Lang }) {
  const date = fmtDate(headlineDate(tv), lang);
  const L = (fr: string, en: string) => t(lang, fr, en);

  const logistics: Fact[] = [
    [L('Interphone', 'Intercom'), label(INTERCOM, lang, tv.intercom_status)],
    [L('Ménage', 'Cleaning'), tv.cleaning_status],
    [L('Télécommande de stationnement', 'Parking remote'), tv.parking_remote_status],
    [L('Stationnement', 'Parking stall'), change(tv.parking_stall_current, tv.parking_stall_new)],
    [L('Meublé', 'Furnished'), change(tv.furnished_status_current, tv.furnished_status_new)],
    [L('Transfert Internet (sortant)', 'Internet transfer (outgoing)'), yesNoPill(lang, tv.internet_transfer_current)],
    [L('Transfert Internet (entrant)', 'Internet transfer (incoming)'), yesNoPill(lang, tv.internet_transfer_new)],
    [L('Pièces', 'Rooms'), tv.room_count],
    [L('Matelas', 'Mattress'), tv.mattress_size],
  ];
  const s = tv.settlement;
  const settlement: Fact[] = s ? [
    [L('Dépôt dû', 'Deposit owed'), fmtMoney(s.deposit_amount_owed, lang)],
    [L('Dépôt reçu', 'Deposit received'), yesNoPill(lang, s.deposit_received)],
    [L('Remboursement du dépôt', 'Deposit refund'), s.deposit_refund_status],
    [L('Montant dû par le locataire', 'Owed by tenant'), fmtMoney(s.amount_owed_by_tenant, lang)],
    [L('Dossier TAL ouvert', 'TAL case open'), yesNoPill(lang, s.tal_dossier_open)],
    [L('État des lieux reçu', 'Inspection report received'), yesNoPill(lang, s.edl_received)],
    [L('État des lieux satisfaisant', 'Inspection satisfactory'), yesNoPill(lang, s.edl_satisfactory)],
    [L('Notes', 'Notes'), s.notes],
  ] : [];
  const hasLogistics = logistics.some(([, v]) => v);
  const hasSettlement = settlement.some(([, v]) => v);
  const hasNotes = !!(tv.pre_departure_inspection_notes || tv.general_notes);
  const mine = <span className={styles.mineTag}>{L('Ce locataire', 'This tenant')}</span>;

  return (
    <article className={styles.turnover} data-testid="turnover-card">
      <div className={styles.turnoverHead}>
        {tv.tenant_role === 'incoming' && (
          <span className={`${styles.role} ${styles.roleIn}`}>{L('Arrivée', 'Move-in')}</span>
        )}
        {tv.tenant_role === 'outgoing' && (
          <span className={`${styles.role} ${styles.roleOut}`}>{L('Départ', 'Move-out')}</span>
        )}
        <span className={styles.turnoverDate}>{date ?? L('Date inconnue', 'Unknown date')}</span>
        {tv.move_reason && (
          <span className={`${styles.chip} ${styles.chipMuted}`}>{label(MOVE_REASON, lang, tv.move_reason)}</span>
        )}
      </div>

      <div className={styles.sides}>
        <section className={`${styles.side} ${tv.tenant_role === 'outgoing' ? styles.sideMine : ''}`}>
          <h4 className={styles.sideTitle}>
            {L('Sortant', 'Outgoing')}{tv.tenant_role === 'outgoing' && mine}
          </h4>
          <p className={styles.sideName}>{tv.outgoing_tenant_name ?? '—'}</p>
          <Facts className={styles.sideFacts} items={[
            [L('Fin du bail', 'Lease end'), fmtDate(tv.lease_end_date ?? tv.outgoing_fin_bail, lang)],
            [L('Cession souhaitée', 'Assignment desired'), fmtDate(tv.assignment_desired_date, lang)],
            [L('Départ confirmé', 'Move-out confirmed'), when(fmtDate(tv.move_out_confirmed_date, lang), fmtTime(tv.move_out_time))],
            [L('Remise des clés', 'Key return'), tv.key_return_method],
            [L('Loyer', 'Rent'), fmtMoney(tv.outgoing_loyer, lang)],
          ]} />
        </section>
        <section className={`${styles.side} ${tv.tenant_role === 'incoming' ? styles.sideMine : ''}`}>
          <h4 className={styles.sideTitle}>
            {L('Entrant', 'Incoming')}{tv.tenant_role === 'incoming' && mine}
          </h4>
          <p className={styles.sideName}>{tv.incoming_tenant_name ?? '—'}</p>
          <Facts className={styles.sideFacts} items={[
            [L('Début du bail', 'Lease start'), fmtDate(tv.lease_start_date, lang)],
            [L('Arrivée confirmée', 'Move-in confirmed'), when(fmtDate(tv.move_in_confirmed_date, lang), fmtTime(tv.move_in_time))],
            [L('Récupération des clés', 'Key pickup'), tv.key_pickup_method],
          ]} />
        </section>
      </div>

      {(hasLogistics || tv.furniture.length > 0 || hasSettlement || hasNotes) && (
      <div className={styles.extras}>
      {hasLogistics && (
        <div className={styles.extra}>
          <h4>{L('Logistique', 'Logistics')}</h4>
          <Facts items={logistics} />
        </div>
      )}
      {tv.furniture.length > 0 && (
        <div className={styles.extra}>
          <h4>{L('Électroménagers et services', 'Appliances and services')}</h4>
          <Facts items={tv.furniture.map((f): Fact => [
            label(APPLIANCE, lang, f.appliance_type) ?? '—',
            change(yesNo(lang, f.included_current), yesNo(lang, f.included_new)),
          ])} />
        </div>
      )}
      {hasSettlement && (
        <div className={styles.extra}>
          <h4>{L('Règlement', 'Settlement')}</h4>
          <Facts items={settlement} />
        </div>
      )}
      {hasNotes && (
        <div className={`${styles.extra} ${styles.extraWide}`}>
          <h4>{L('Notes', 'Notes')}</h4>
          {tv.pre_departure_inspection_notes && <p className={styles.notes}>{tv.pre_departure_inspection_notes}</p>}
          {tv.general_notes && <p className={styles.notes}>{tv.general_notes}</p>}
        </div>
      )}
      </div>
      )}
    </article>
  );
}

interface Props {
  unitId: number;
  tenantId: number;
  /** Shown while the turnover loads, from the unit page that opened the panel. */
  tenant?: PortfolioTenant;
  lang: Lang;
  onClose: () => void;
}

export default function TurnoverDialog({ unitId, tenantId, tenant: initial, lang, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['portfolio', 'turnover', unitId, tenantId],
    queryFn: () => fetchTenantTurnover(unitId, tenantId),
  });
  const tenant = data?.tenant ?? initial;
  const L = (fr: string, en: string) => t(lang, fr, en);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return; }
      // Keep Tab inside the window while it is open.
      if (e.key !== 'Tab' || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), summary, [tabindex]:not([tabindex="-1"])');
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    // The page behind stays put while the window scrolls.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, [onClose]);

  return (
    <div className={styles.scrim} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section ref={dialogRef} className={styles.dialog} role="dialog" aria-modal="true"
               aria-labelledby="turnover-title" data-testid="turnover-dialog">
        <header className={styles.dialogHead}>
          <div>
            <p className={styles.eyebrow}>{L('Roulement du locataire', 'Tenant turnover')}</p>
            <h2 id="turnover-title" className={styles.dialogTitle}>
              {tenant?.nom_complet ?? L('Locataire', 'Tenant')}
            </h2>
            {tenant && capaciteLabel(lang, tenant.capacite) && (
              <p className={styles.dialogRole}>{capaciteLabel(lang, tenant.capacite)}</p>
            )}
            {tenant && (tenant.telephone || tenant.courriel) && (
              <div className={styles.dialogContacts} data-testid="turnover-contacts">
                {tenant.telephone && (
                  <a className={styles.contact} href={telHref(tenant.telephone_international ?? tenant.telephone)}
                     aria-label={`${L('Appeler', 'Call')} ${formatPhone(tenant.telephone)}`}>
                    <span className={styles.contactIcon}><PhoneIcon /></span>{formatPhone(tenant.telephone)}
                  </a>
                )}
                {tenant.courriel && (
                  <a className={styles.contact} href={`mailto:${tenant.courriel}`}
                     aria-label={`${L('Écrire à', 'Email')} ${tenant.courriel}`}>
                    <span className={styles.contactIcon}><MailIcon /></span>{tenant.courriel}
                  </a>
                )}
              </div>
            )}
          </div>
          <button ref={closeRef} className={styles.close} onClick={onClose}
                  aria-label={L('Fermer', 'Close')} data-testid="turnover-close">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className={styles.dialogBody}>
          {isLoading && <><div className={styles.skeleton} /><div className={styles.skeleton} /></>}
          {isError && (
            <div className={styles.error} role="alert">
              {L('Impossible de charger le roulement', 'Could not load the turnover')}
              <button className={styles.btn} onClick={() => refetch()}>{L('Réessayer', 'Retry')}</button>
            </div>
          )}
          {data && (
            <>
              <h3 className={styles.sectionTitle}>
                {L('Arrivées et départs', 'Move-ins and move-outs')}
              </h3>
              {data.turnovers.length === 0 ? (
                <p className={styles.empty} data-testid="turnover-empty">
                  {L('Aucun roulement enregistré pour ce locataire dans ce logement.',
                     'No turnover recorded for this tenant in this unit.')}
                </p>
              ) : (
                data.turnovers.map((tv) => <TurnoverCard key={tv.turnover_id} tv={tv} lang={lang} />)
              )}

              {data.other_turnovers.length > 0 && (
                <details className={styles.others} open={data.turnovers.length === 0}>
                  <summary>
                    <svg className={styles.othersChevron} viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"
                         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M8 5l5 5-5 5" />
                    </svg>
                    {L('Autres roulements de ce logement', 'Other turnovers for this unit')}
                    {` (${data.other_turnovers.length})`}
                  </summary>
                  <div>
                    {data.other_turnovers.map((tv) => <TurnoverCard key={tv.turnover_id} tv={tv} lang={lang} />)}
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
