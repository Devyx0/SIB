import { useState } from 'react';
import {
  addOccupant, endLease, endOccupant, startLease, takeoverOccupant, updateTenancy,
} from '../../api/client';
import type { OccupantSeed, PortfolioLease, PortfolioTenant, TenancyCapacity, TenancyFields } from '../../api/client';
import FormDialog, { Field, FieldGroup, inputClass } from '../../components/FormDialog';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { diff, isEmptyPatch } from './editing';
import { todayIso } from './format';
import { useSubmit } from './forms';
import styles from './Portfolio.module.css';

export const CAPACITE_OPTIONS: { value: TenancyCapacity; fr: string; en: string }[] = [
  { value: 'named_on_lease', fr: 'Signataire du bail', en: 'Named on lease' },
  { value: 'added_occupant', fr: 'Occupant ajouté', en: 'Added occupant' },
  { value: 'took_over', fr: 'Cessionnaire', en: 'Took over the lease' },
];

export function capaciteOptionLabel(lang: Lang, value: string | null | undefined): string | null {
  if (!value) return null;
  const hit = CAPACITE_OPTIONS.find((c) => c.value === value);
  return hit ? t(lang, hit.fr, hit.en) : value;
}

/** Max occupants from unit.grandeur leading integer ("3 1/2" → 3). null = unknown / uncapped. */
export function maxOccupantsFromGrandeur(grandeur: string | null | undefined): number | null {
  if (!grandeur) return null;
  const m = /^\s*(\d+)/.exec(grandeur.replace(/½/g, ' 1/2'));
  if (!m) return null;
  const n = Number(m[1]);
  return n > 0 ? n : null;
}

const blank = (s: string) => s.trim() || null;

type OccupantDraft = {
  nom_complet: string;
  telephone: string;
  courriel: string;
  capacite: TenancyCapacity;
};

const emptyOccupant = (capacite: TenancyCapacity): OccupantDraft => ({
  nom_complet: '', telephone: '', courriel: '', capacite,
});

function OccupantFields({ draft, setDraft, lang, capaciteHint }: {
  draft: OccupantDraft;
  setDraft: (f: (d: OccupantDraft) => OccupantDraft) => void;
  lang: Lang;
  capaciteHint?: string;
}) {
  const set = (k: keyof OccupantDraft) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));
  return (
    <>
      <Field label={t(lang, 'Nom complet *', 'Full name *')} wide>
        <input className={inputClass} value={draft.nom_complet} onChange={set('nom_complet')}
               required maxLength={200} name="nom_complet" />
      </Field>
      <Field label={t(lang, 'Téléphone', 'Phone')}>
        <input className={inputClass} value={draft.telephone} onChange={set('telephone')}
               maxLength={50} inputMode="tel" name="telephone" />
      </Field>
      <Field label={t(lang, 'Courriel', 'Email')}>
        <input className={inputClass} value={draft.courriel} onChange={set('courriel')}
               maxLength={200} type="email" name="courriel" />
      </Field>
      <Field label={t(lang, 'Capacité', 'Capacity')} wide hint={capaciteHint}>
        <Select className={inputClass} value={draft.capacite}
                aria-label={t(lang, 'Capacité', 'Capacity')}
                onChange={(e) => setDraft((d) => ({ ...d, capacite: e.target.value as TenancyCapacity }))}>
          {CAPACITE_OPTIONS.map((c) => (
            <option key={c.value} value={c.value}>{t(lang, c.fr, c.en)}</option>
          ))}
        </Select>
      </Field>
    </>
  );
}

function toNewTenant(draft: OccupantDraft): OccupantSeed {
  return {
    new_tenant: {
      nom_complet: draft.nom_complet.trim(),
      telephone: blank(draft.telephone),
      courriel: blank(draft.courriel),
    },
    capacite: draft.capacite,
  };
}

type ToastFn = (message: string) => void;

// ── Edit tenancy ─────────────────────────────────────────────────────────────

export function EditTenancyDialog({ tenant, lang, onClose, onToast }: {
  tenant: PortfolioTenant; lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, run } = useSubmit(lang, onClose);
  const initial: TenancyFields = {
    capacite: (tenant.capacite as TenancyCapacity | null) ?? null,
    reason_for_change: tenant.reason_for_change ?? null,
    start_date: tenant.start_date ?? null,
    end_date: tenant.end_date ?? null,
  };
  const [draft, setDraft] = useState(initial);

  function submit() {
    const tenancyId = tenant.tenancy_id;
    if (tenancyId == null) return;
    const patch = diff(initial, draft);
    if (isEmptyPatch(patch)) { onClose(); return; }
    run(() => updateTenancy(tenancyId, patch), () => {
      onToast?.(t(lang, 'Occupation mise à jour.', 'Occupancy updated.'));
    });
  }

  return (
    <FormDialog
      lang={lang}
      testId="edit-tenancy-dialog"
      eyebrow={t(lang, 'Occupation', 'Occupancy')}
      title={t(lang, 'Modifier l’occupation', 'Edit occupancy')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'Locataire', 'Tenant')} wide>
          <input className={inputClass} value={tenant.nom_complet ?? ''} readOnly />
        </Field>
        <Field label={t(lang, 'Capacité', 'Capacity')}>
          <Select className={inputClass} value={draft.capacite ?? ''}
                  data-testid="tenancy-capacite"
                  aria-label={t(lang, 'Capacité', 'Capacity')}
                  onChange={(e) => setDraft((d) => ({
                    ...d, capacite: (e.target.value || null) as TenancyCapacity | null,
                  }))}>
            {CAPACITE_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>{t(lang, c.fr, c.en)}</option>
            ))}
          </Select>
        </Field>
        <Field label={t(lang, 'Date de début', 'Start date')}>
          <input className={inputClass} type="date" value={draft.start_date ?? ''}
                 onChange={(e) => setDraft((d) => ({ ...d, start_date: e.target.value || null }))} />
        </Field>
        <Field label={t(lang, 'Date de fin', 'End date')}
               hint={t(lang, 'Pour retirer le locataire, préférez « Retirer ».',
                             'To remove the occupant, prefer “Remove”.')}>
          <input className={inputClass} type="date" value={draft.end_date ?? ''}
                 onChange={(e) => setDraft((d) => ({ ...d, end_date: e.target.value || null }))} />
        </Field>
        <Field label={t(lang, 'Motif du changement', 'Reason for change')} wide>
          <input className={inputClass} value={draft.reason_for_change ?? ''} maxLength={500}
                 onChange={(e) => setDraft((d) => ({ ...d, reason_for_change: e.target.value }))} />
        </Field>
      </FieldGroup>
    </FormDialog>
  );
}

// ── Add occupant ─────────────────────────────────────────────────────────────

export function AddOccupantDialog({ unitId, activeCount, maxOccupants, lang, onClose, onToast }: {
  unitId: number; activeCount: number; maxOccupants: number | null;
  lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, setError, run } = useSubmit(lang, onClose);
  const [draft, setDraft] = useState(emptyOccupant('added_occupant'));
  const [startDate, setStartDate] = useState(todayIso());
  const [reason, setReason] = useState('');
  const atCapacity = maxOccupants != null && activeCount >= maxOccupants;

  function submit() {
    if (atCapacity) {
      setError(t(lang,
        `Ce logement est limité à ${maxOccupants} occupant(s).`,
        `This unit is limited to ${maxOccupants} occupant(s).`));
      return;
    }
    run(() => addOccupant(unitId, {
      ...toNewTenant(draft),
      start_date: startDate || null,
      reason_for_change: blank(reason),
    }), () => {
      onToast?.(t(lang, 'Occupant ajouté.', 'Occupant added.'));
    });
  }

  return (
    <FormDialog
      lang={lang}
      testId="add-occupant-dialog"
      eyebrow={t(lang, 'Occupation', 'Occupancy')}
      title={t(lang, 'Ajouter un occupant', 'Add occupant')}
      submitLabel={t(lang, 'Ajouter', 'Add')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup title={t(lang, 'Nouveau locataire', 'New tenant')}>
        {atCapacity && (
          <Field label="" wide>
            <p className={styles.inlineHint} role="status" data-testid="at-capacity-hint">
              {t(lang,
                `Capacité atteinte (${maxOccupants}). Impossible d’ajouter un occupant.`,
                `At capacity (${maxOccupants}). Cannot add an occupant.`)}
            </p>
          </Field>
        )}
        <OccupantFields draft={draft} setDraft={(f) => setDraft(f(draft))} lang={lang} />
        <Field label={t(lang, 'Date de début', 'Start date')}>
          <input className={inputClass} type="date" value={startDate}
                 onChange={(e) => setStartDate(e.target.value)} />
        </Field>
        <Field label={t(lang, 'Motif', 'Reason')}>
          <input className={inputClass} value={reason} maxLength={500}
                 onChange={(e) => setReason(e.target.value)} />
        </Field>
      </FieldGroup>
    </FormDialog>
  );
}

// ── Takeover ─────────────────────────────────────────────────────────────────

export function TakeoverDialog({ unitId, outgoing, activeCount, maxOccupants, lang, onClose, onToast }: {
  unitId: number; outgoing: PortfolioTenant;
  activeCount: number; maxOccupants: number | null;
  lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, setError, run } = useSubmit(lang, onClose);
  const [draft, setDraft] = useState(emptyOccupant('took_over'));
  const [effectiveDate, setEffectiveDate] = useState(todayIso());
  const [reason, setReason] = useState('');

  function submit() {
    const outgoingId = outgoing.tenancy_id;
    if (outgoingId == null) return;
    // Net zero when effective today; if effective later, count briefly rises by 1.
    const endsToday = effectiveDate <= todayIso();
    const resulting = activeCount - (endsToday ? 1 : 0) + 1;
    if (maxOccupants != null && resulting > maxOccupants) {
      setError(t(lang,
        `Ce logement est limité à ${maxOccupants} occupant(s).`,
        `This unit is limited to ${maxOccupants} occupant(s).`));
      return;
    }
    run(() => takeoverOccupant(unitId, {
      outgoing_tenancy_id: outgoingId,
      ...toNewTenant(draft),
      effective_date: effectiveDate,
      reason_for_change: blank(reason),
    }), () => {
      onToast?.(t(lang, 'Cession enregistrée.', 'Takeover saved.'));
    });
  }

  return (
    <FormDialog
      lang={lang}
      testId="takeover-dialog"
      eyebrow={t(lang, 'Cession de bail', 'Lease takeover')}
      title={t(lang, 'Reprendre l’occupation', 'Take over occupancy')}
      submitLabel={t(lang, 'Céder', 'Take over')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'Occupant sortant', 'Outgoing occupant')} wide
               hint={t(lang, 'Cette occupation sera close à la date d’effet.',
                             'This occupancy will close on the effective date.')}>
          <input className={inputClass} value={outgoing.nom_complet ?? ''} readOnly />
        </Field>
        <Field label={t(lang, 'Date d’effet *', 'Effective date *')}>
          <input className={inputClass} type="date" required value={effectiveDate}
                 onChange={(e) => setEffectiveDate(e.target.value)} name="effective_date" />
        </Field>
        <Field label={t(lang, 'Motif', 'Reason')}>
          <input className={inputClass} value={reason} maxLength={500}
                 onChange={(e) => setReason(e.target.value)} />
        </Field>
      </FieldGroup>
      <FieldGroup title={t(lang, 'Occupant entrant', 'Incoming occupant')}>
        <OccupantFields draft={draft} setDraft={(f) => setDraft(f(draft))} lang={lang} />
      </FieldGroup>
    </FormDialog>
  );
}

// ── End occupant ─────────────────────────────────────────────────────────────

export function EndOccupantDialog({ unitId, tenant, activeCount, lang, onClose, onToast }: {
  unitId: number; tenant: PortfolioTenant; activeCount: number;
  lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, setError, run } = useSubmit(lang, onClose);
  const [endDate, setEndDate] = useState(todayIso());
  const [reason, setReason] = useState('');
  const isLast = activeCount <= 1;
  const lastMsg = t(lang,
    'Impossible de retirer le dernier occupant — terminez le bail à la place.',
    'Cannot remove the last occupant — end the lease instead.');

  function submit() {
    const tenancyId = tenant.tenancy_id;
    if (tenancyId == null) return;
    if (isLast) {
      setError(lastMsg);
      return;
    }
    run(() => endOccupant(unitId, tenancyId, {
      end_date: endDate || null,
      reason_for_change: blank(reason),
      current_end_date: tenant.end_date ?? null,
    }), () => {
      onToast?.(t(lang, 'Occupant retiré.', 'Occupant removed.'));
    });
  }

  return (
    <FormDialog
      lang={lang}
      testId="end-occupant-dialog"
      eyebrow={t(lang, 'Occupation', 'Occupancy')}
      title={t(lang, 'Retirer l’occupant', 'Remove occupant')}
      submitLabel={t(lang, 'Retirer', 'Remove')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'Locataire', 'Tenant')} wide
               hint={isLast
                 ? lastMsg
                 : t(lang, 'Le locataire quittera ce bail; le bail reste en cours.',
                           'The tenant will leave this lease; the lease stays current.')}>
          <input className={inputClass} value={tenant.nom_complet ?? ''} readOnly />
        </Field>
        {isLast && (
          <Field label="" wide>
            <p className={styles.inlineHint} role="status" data-testid="last-occupant-hint">
              {lastMsg}
            </p>
          </Field>
        )}
        <Field label={t(lang, 'Date de fin', 'End date')}>
          <input className={inputClass} type="date" value={endDate}
                 onChange={(e) => setEndDate(e.target.value)} disabled={isLast} />
        </Field>
        <Field label={t(lang, 'Motif', 'Reason')}>
          <input className={inputClass} value={reason} maxLength={500}
                 onChange={(e) => setReason(e.target.value)} disabled={isLast} />
        </Field>
      </FieldGroup>
    </FormDialog>
  );
}

// ── End lease ────────────────────────────────────────────────────────────────

export function EndLeaseDialog({ unitId, lease, lang, onClose, onToast }: {
  unitId: number; lease: PortfolioLease; lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, run } = useSubmit(lang, onClose);
  const [finBail, setFinBail] = useState(todayIso());
  const [statut, setStatut] = useState('Terminé');
  const [closeTenancies, setCloseTenancies] = useState(true);

  function submit() {
    run(() => endLease(unitId, {
      fin_bail: finBail,
      statut: blank(statut),
      current_fin_bail: lease.fin_bail,
      current_statut: lease.statut,
      close_tenancies: closeTenancies,
    }), () => {
      onToast?.(t(lang, 'Bail terminé.', 'Lease ended.'));
    });
  }

  return (
    <FormDialog
      lang={lang}
      testId="end-lease-dialog"
      eyebrow={t(lang, 'Bail', 'Lease')}
      title={t(lang, 'Terminer le bail', 'End the lease')}
      submitLabel={t(lang, 'Terminer le bail', 'End lease')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'Date de fin *', 'End date *')} wide
               hint={t(lang, 'Le bail ne sera plus considéré comme courant.',
                             'The lease will no longer be treated as current.')}>
          <input className={inputClass} type="date" required value={finBail}
                 onChange={(e) => setFinBail(e.target.value)} name="fin_bail" />
        </Field>
        <Field label={t(lang, 'Statut', 'Status')}>
          <input className={inputClass} value={statut} maxLength={100}
                 onChange={(e) => setStatut(e.target.value)} />
        </Field>
        <Field label={t(lang, 'Occupants', 'Occupants')} wide>
          <span className={styles.checkRow}>
            <input type="checkbox" checked={closeTenancies}
                   onChange={(e) => setCloseTenancies(e.target.checked)}
                   data-testid="close-tenancies" />
            {t(lang, 'Clore aussi les occupations en cours', 'Also close current occupancies')}
          </span>
        </Field>
      </FieldGroup>
    </FormDialog>
  );
}

// ── Start lease ──────────────────────────────────────────────────────────────

export function StartLeaseDialog({ unitId, currentLease, maxOccupants, lang, onClose, onToast }: {
  unitId: number; currentLease: PortfolioLease | null; maxOccupants: number | null;
  lang: Lang; onClose: () => void; onToast?: ToastFn;
}) {
  const { submitting, error, setError, run } = useSubmit(lang, onClose);
  const [debut, setDebut] = useState(todayIso());
  const [fin, setFin] = useState('');
  const [statut, setStatut] = useState('Actif');
  const [langue, setLangue] = useState('');
  const [endPrevious, setEndPrevious] = useState(false);
  const [occupants, setOccupants] = useState<OccupantDraft[]>([
    emptyOccupant('named_on_lease'),
  ]);

  function submit() {
    const seeds = occupants
      .filter((o) => o.nom_complet.trim())
      .map(toNewTenant);
    if (seeds.length === 0) {
      setError(t(lang,
        'Au moins un occupant est requis pour démarrer un bail.',
        'At least one occupant is required to start a lease.'));
      return;
    }
    if (maxOccupants != null && seeds.length > maxOccupants) {
      setError(t(lang,
        `Ce logement est limité à ${maxOccupants} occupant(s).`,
        `This unit is limited to ${maxOccupants} occupant(s).`));
      return;
    }
    run(() => startLease(unitId, {
      debut_bail: debut,
      fin_bail: fin || null,
      statut: blank(statut) ?? 'Actif',
      langue_bail: blank(langue),
      occupants: seeds,
      end_previous: currentLease ? endPrevious : false,
    }), () => {
      onToast?.(t(lang, 'Bail démarré.', 'Lease started.'));
    });
  }

  const canAddMore = maxOccupants == null || occupants.length < maxOccupants;

  return (
    <FormDialog
      lang={lang}
      testId="start-lease-dialog"
      eyebrow={t(lang, 'Bail', 'Lease')}
      title={t(lang, 'Démarrer un bail', 'Start a lease')}
      submitLabel={t(lang, 'Démarrer le bail', 'Start lease')}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      {currentLease && (
        <FieldGroup title={t(lang, 'Bail en cours', 'Current lease')}>
          <Field label={t(lang, 'Clôture', 'Close-out')} wide
                 hint={t(lang, 'Obligatoire : un seul bail peut être courant.',
                               'Required: only one lease can be current.')}>
            <span className={styles.checkRow}>
              <input type="checkbox" required checked={endPrevious}
                     onChange={(e) => setEndPrevious(e.target.checked)}
                     data-testid="end-previous-lease" />
              {t(lang, 'Clore le bail actuel et ses occupants', 'End the current lease and its occupants')}
            </span>
          </Field>
        </FieldGroup>
      )}
      <FieldGroup title={t(lang, 'Nouveau bail', 'New lease')}>
        <Field label={t(lang, 'Début *', 'Start *')}>
          <input className={inputClass} type="date" required value={debut}
                 onChange={(e) => setDebut(e.target.value)} name="debut_bail" />
        </Field>
        <Field label={t(lang, 'Fin', 'End')}>
          <input className={inputClass} type="date" value={fin}
                 onChange={(e) => setFin(e.target.value)} />
        </Field>
        <Field label={t(lang, 'Statut', 'Status')}>
          <input className={inputClass} value={statut} maxLength={100}
                 onChange={(e) => setStatut(e.target.value)} />
        </Field>
        <Field label={t(lang, 'Langue', 'Language')}>
          <input className={inputClass} value={langue} maxLength={50}
                 onChange={(e) => setLangue(e.target.value)} />
        </Field>
      </FieldGroup>
      {occupants.map((occ, i) => (
        <FieldGroup key={i} title={t(lang, `Occupant ${i + 1}`, `Occupant ${i + 1}`)}>
          <OccupantFields
            draft={occ}
            lang={lang}
            setDraft={(f) => setOccupants((list) => list.map((o, j) => (j === i ? f(o) : o)))}
          />
          {occupants.length > 1 && (
            <div className={styles.wideAction}>
              <button type="button" className={styles.linkBtn}
                      onClick={() => setOccupants((list) => list.filter((_, j) => j !== i))}>
                {t(lang, 'Retirer cet occupant', 'Remove this occupant')}
              </button>
            </div>
          )}
        </FieldGroup>
      ))}
      {canAddMore && (
        <div className={styles.wideAction}>
          <button type="button" className={styles.linkBtn} data-testid="start-lease-add-occupant"
                  onClick={() => setOccupants((list) => [
                    ...list,
                    emptyOccupant(list.length === 0 ? 'named_on_lease' : 'added_occupant'),
                  ])}>
            {t(lang, '+ Ajouter un occupant au bail', '+ Add an occupant to the lease')}
          </button>
        </div>
      )}
    </FormDialog>
  );
}
