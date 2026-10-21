import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import {
  createBuildingDocument, createPaintSpec, deleteBuildingDocument, deletePaintSpec,
  setFicheEntry, updateBuilding, updatePaintSpec,
} from '../../api/client';
import type {
  BuildingFields, BuildingReference, PaintSpec, PaintSpecFields, PortfolioBuildingDetail,
} from '../../api/client';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { diff, errorText, isEmptyPatch } from './editing';
import { matches } from './format';
import { LinkOutIcon, PencilIcon, PlusIcon, TrashIcon } from './icons';
import styles from './BuildingInfo.module.css';

// Everything staff used to look up in the building's Drive folder — the fiche
// technique, the paint chart, the characteristics — kept and edited here.

type Ref = keyof BuildingReference;
type FieldKind = 'text' | 'long' | 'bool' | 'int';

const REFERENCE_FIELDS: { key: Ref; fr: string; en: string; kind: FieldKind }[] = [
  { key: 'chauffage', fr: 'Chauffage', en: 'Heating', kind: 'text' },
  { key: 'chauffage_details', fr: 'Détails du chauffage', en: 'Heating details', kind: 'long' },
  { key: 'chauffe_eau', fr: 'Chauffe-eau', en: 'Water heater', kind: 'text' },
  { key: 'systeme_incendie', fr: 'Système incendie', en: 'Fire system', kind: 'text' },
  { key: 'boite_a_cle_ext', fr: 'Boîte à clés extérieure', en: 'Outdoor key box', kind: 'text' },
  { key: 'boite_a_cle_int', fr: 'Boîte à clés intérieure', en: 'Indoor key box', kind: 'text' },
  { key: 'internet', fr: 'Internet', en: 'Internet', kind: 'text' },
  { key: 'furnished', fr: 'Meublé', en: 'Furnished', kind: 'text' },
  { key: 'building_structure', fr: 'Structure', en: 'Structure', kind: 'text' },
  { key: 'property_type', fr: 'Type de propriété', en: 'Property type', kind: 'text' },
  { key: 'ascenseur', fr: 'Ascenseur', en: 'Elevator', kind: 'bool' },
  { key: 'nb_elevateurs', fr: "Nombre d'ascenseurs", en: 'Elevators', kind: 'int' },
  { key: 'piscine', fr: 'Piscine', en: 'Pool', kind: 'bool' },
  { key: 'sauna', fr: 'Sauna', en: 'Sauna', kind: 'bool' },
  { key: 'gym', fr: 'Gym', en: 'Gym', kind: 'bool' },
  { key: 'dogs_allowed', fr: 'Chiens permis', en: 'Dogs allowed', kind: 'bool' },
];

const PAINT_FIELDS: { key: keyof PaintSpecFields; fr: string; en: string }[] = [
  { key: 'zone', fr: 'Zone', en: 'Area' },
  { key: 'surface_label', fr: 'Surface', en: 'Surface' },
  { key: 'product_interior', fr: 'Produit intérieur', en: 'Interior product' },
  { key: 'product_exterior', fr: 'Produit extérieur', en: 'Exterior product' },
  { key: 'manufacturer', fr: 'Fabricant', en: 'Manufacturer' },
];

const EMPTY_PAINT: PaintSpecFields = {
  zone: null, surface_label: null, product_interior: null, product_exterior: null, manufacturer: null,
};

function yesNo(v: boolean | null | undefined, lang: Lang) {
  return v == null ? null : v ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No');
}

/** Refreshes everything that shows building info after a save. */
function useRefresh(buildingId: number) {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: ['portfolio', 'building', buildingId] }),
    qc.invalidateQueries({ queryKey: ['portfolio', 'unit'] }),
    qc.invalidateQueries({ queryKey: ['portfolio', 'search'] }),
  ]);
}

/** Runs a save, keeping busy / error state for the card. */
function useSave(lang: Lang) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(errorText(err, lang));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}

function CardHead({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className={styles.cardHead}>
      <div>
        <h3 className={styles.cardTitle}>{title}</h3>
        {hint && <p className={styles.hint}>{hint}</p>}
      </div>
      {action}
    </div>
  );
}

function IconButton({ label, onClick, children, testId, danger }: {
  label: string; onClick: () => void; children: React.ReactNode; testId?: string; danger?: boolean;
}) {
  return (
    <button type="button" className={`${styles.iconBtn} ${danger ? styles.iconBtnDanger : ''}`}
            onClick={onClick} aria-label={label} title={label} data-testid={testId}>
      {children}
    </button>
  );
}

function Actions({ lang, busy, onCancel, saveLabel }: {
  lang: Lang; busy: boolean; onCancel: () => void; saveLabel?: string;
}) {
  return (
    <div className={styles.actions}>
      <button type="submit" className={styles.primary} disabled={busy}>
        {busy ? t(lang, 'Enregistrement…', 'Saving…') : saveLabel ?? t(lang, 'Enregistrer', 'Save')}
      </button>
      <button type="button" className={styles.secondary} onClick={onCancel} disabled={busy}>
        {t(lang, 'Annuler', 'Cancel')}
      </button>
    </div>
  );
}

// ── Characteristics ──────────────────────────────────────────────────────────

function Characteristics({ building, lang }: { building: PortfolioBuildingDetail; lang: Lang }) {
  const refresh = useRefresh(building.building_id);
  const { busy, error, setError, run } = useSave(lang);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<BuildingReference>(building.reference);
  useEffect(() => { if (!editing) setDraft(building.reference); }, [building.reference, editing]);

  const filled = REFERENCE_FIELDS.filter((f) => building.reference[f.key] != null && building.reference[f.key] !== '');
  const show = (f: typeof REFERENCE_FIELDS[number]) => {
    const v = building.reference[f.key];
    return f.kind === 'bool' ? yesNo(v as boolean | null, lang) : String(v);
  };

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const patch = diff(building.reference as BuildingFields, draft as BuildingFields);
    if (isEmptyPatch(patch)) { setEditing(false); return; }
    if (await run(() => updateBuilding(building.building_id, patch).then(refresh))) setEditing(false);
  }

  const set = (key: Ref, value: string | number | boolean | null) => setDraft((d) => ({ ...d, [key]: value }));

  return (
    <section className={styles.card} data-testid="building-characteristics">
      <CardHead
        title={t(lang, 'Caractéristiques', 'Characteristics')}
        action={!editing && (
          <IconButton label={t(lang, 'Modifier les caractéristiques', 'Edit characteristics')}
                      onClick={() => { setError(null); setEditing(true); }} testId="edit-characteristics">
            <PencilIcon />
          </IconButton>
        )}
      />
      {editing ? (
        <form onSubmit={save} className={styles.form}>
          <div className={styles.formGrid}>
            {REFERENCE_FIELDS.map((f) => (
              <label key={f.key} className={`${styles.field} ${f.kind === 'long' ? styles.fieldWide : ''}`}>
                <span className={styles.fieldLabel}>{t(lang, f.fr, f.en)}</span>
                {f.kind === 'bool' ? (
                  <Select className={styles.input} value={draft[f.key] == null ? '' : String(draft[f.key])}
                          aria-label={t(lang, f.fr, f.en)}
                          onChange={(e) => set(f.key, e.target.value === '' ? null : e.target.value === 'true')}>
                    <option value="">—</option>
                    <option value="true">{t(lang, 'Oui', 'Yes')}</option>
                    <option value="false">{t(lang, 'Non', 'No')}</option>
                  </Select>
                ) : f.kind === 'long' ? (
                  <textarea className={styles.input} rows={3} value={(draft[f.key] as string | null) ?? ''}
                            onChange={(e) => set(f.key, e.target.value)} />
                ) : (
                  <input className={styles.input} type={f.kind === 'int' ? 'number' : 'text'} min={0}
                         value={(draft[f.key] as string | number | null) ?? ''}
                         onChange={(e) => set(f.key, f.kind === 'int'
                           ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)} />
                )}
              </label>
            ))}
          </div>
          {error && <p className={styles.error} role="alert">{error}</p>}
          <Actions lang={lang} busy={busy} onCancel={() => setEditing(false)} />
        </form>
      ) : filled.length > 0 ? (
        <dl className={styles.facts}>
          {filled.map((f) => (
            <div key={f.key} className={styles.fact}>
              <dt>{t(lang, f.fr, f.en)}</dt>
              <dd>{show(f)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className={styles.empty}>{t(lang, 'Aucune caractéristique saisie.', 'No characteristics yet.')}</p>
      )}
    </section>
  );
}

// ── Paint ────────────────────────────────────────────────────────────────────

function PaintRowForm({ initial, lang, busy, error, onSave, onCancel }: {
  initial: PaintSpecFields; lang: Lang; busy: boolean; error: string | null;
  onSave: (draft: PaintSpecFields) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <form className={styles.paintForm} data-testid="paint-form"
          onSubmit={(e) => { e.preventDefault(); onSave(draft); }}>
      {PAINT_FIELDS.map((f, i) => (
        <label key={f.key} className={styles.field}>
          <span className={styles.fieldLabel}>{t(lang, f.fr, f.en)}</span>
          <input className={styles.input} value={draft[f.key] ?? ''} autoFocus={i === 0}
                 onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))} />
        </label>
      ))}
      {error && <p className={styles.error} role="alert">{error}</p>}
      <Actions lang={lang} busy={busy} onCancel={onCancel} />
    </form>
  );
}

function Paint({ building, lang }: { building: PortfolioBuildingDetail; lang: Lang }) {
  const refresh = useRefresh(building.building_id);
  const { busy, error, setError, run } = useSave(lang);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const specs = building.paint_specs;

  const start = (id: number | 'new') => { setError(null); setEditing(id); };
  const fields = (s: PaintSpec): PaintSpecFields => ({
    zone: s.zone, surface_label: s.surface_label, product_interior: s.product_interior,
    product_exterior: s.product_exterior, manufacturer: s.manufacturer,
  });

  async function saveNew(draft: PaintSpecFields) {
    if (await run(() => createPaintSpec(building.building_id, draft).then(refresh))) setEditing(null);
  }
  async function saveEdit(spec: PaintSpec, draft: PaintSpecFields) {
    const patch = diff(fields(spec), draft);
    if (isEmptyPatch(patch)) { setEditing(null); return; }
    if (await run(() => updatePaintSpec(spec.paint_spec_id, patch).then(refresh))) setEditing(null);
  }
  async function remove(spec: PaintSpec) {
    const what = [spec.zone, spec.surface_label].filter(Boolean).join(' — ') || t(lang, 'cette ligne', 'this line');
    if (!window.confirm(t(lang, `Supprimer « ${what} » ?`, `Delete “${what}”?`))) return;
    await run(() => deletePaintSpec(spec.paint_spec_id).then(refresh));
  }

  return (
    <section className={styles.card} data-testid="building-paint">
      <CardHead
        title={t(lang, 'Peinture', 'Paint')}
        hint={t(lang, 'Codes et produits par zone (charte de peinture).', 'Codes and products by area (paint chart).')}
        action={editing === null && (
          <button type="button" className={styles.addBtn} onClick={() => start('new')} data-testid="add-paint">
            <PlusIcon size={14} /> {t(lang, 'Ajouter', 'Add')}
          </button>
        )}
      />
      {editing === 'new' && (
        <PaintRowForm initial={EMPTY_PAINT} lang={lang} busy={busy} error={error}
                      onSave={saveNew} onCancel={() => setEditing(null)} />
      )}
      {specs.length === 0 && editing !== 'new' ? (
        <p className={styles.empty}>{t(lang, 'Aucune spécification de peinture.', 'No paint specification.')}</p>
      ) : (
        <ul className={styles.paintList}>
          {specs.map((s) => (
            <li key={s.paint_spec_id} className={styles.paintRow} data-testid="paint-row">
              {editing === s.paint_spec_id ? (
                <PaintRowForm initial={fields(s)} lang={lang} busy={busy} error={error}
                              onSave={(d) => saveEdit(s, d)} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <div className={styles.paintMain}>
                    <span className={styles.paintWhere}>
                      {[s.zone, s.surface_label].filter(Boolean).join(' · ') || '—'}
                    </span>
                    <span className={styles.paintProduct}>
                      {[s.product_interior, s.product_exterior].filter(Boolean).join(' / ') || '—'}
                    </span>
                    {s.manufacturer && <span className={styles.paintMaker}>{s.manufacturer}</span>}
                  </div>
                  <div className={styles.rowTools}>
                    <IconButton label={t(lang, 'Modifier', 'Edit')} onClick={() => start(s.paint_spec_id)}
                                testId="edit-paint"><PencilIcon /></IconButton>
                    <IconButton label={t(lang, 'Supprimer', 'Delete')} onClick={() => remove(s)} danger>
                      <TrashIcon />
                    </IconButton>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && editing === null && <p className={styles.error} role="alert">{error}</p>}
    </section>
  );
}

// ── Fiche technique (free-form label → value lines) ──────────────────────────

function FicheForm({ lang, label, value, fixedLabel, busy, error, onSave, onCancel }: {
  lang: Lang; label: string; value: string; fixedLabel: boolean; busy: boolean; error: string | null;
  onSave: (label: string, value: string) => void; onCancel: () => void;
}) {
  const [l, setL] = useState(label);
  const [v, setV] = useState(value);
  const rows = Math.min(8, Math.max(2, v.split('\n').length));
  return (
    <form className={styles.ficheForm} data-testid="fiche-form"
          onSubmit={(e) => { e.preventDefault(); if (l.trim()) onSave(l.trim(), v); }}>
      {!fixedLabel && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t(lang, 'Libellé', 'Label')}</span>
          <input className={styles.input} value={l} onChange={(e) => setL(e.target.value)} autoFocus required
                 placeholder={t(lang, 'p. ex. Code de peinture', 'e.g. Paint code')} />
        </label>
      )}
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{fixedLabel ? l : t(lang, 'Valeur', 'Value')}</span>
        <textarea className={styles.input} rows={rows} value={v} autoFocus={fixedLabel}
                  onChange={(e) => setV(e.target.value)} />
      </label>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <Actions lang={lang} busy={busy} onCancel={onCancel} />
    </form>
  );
}

function Fiche({ building, lang }: { building: PortfolioBuildingDetail; lang: Lang }) {
  const refresh = useRefresh(building.building_id);
  const { busy, error, setError, run } = useSave(lang);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState('');
  const entries = building.fiche.filter((e) => matches(q, e.label, e.value));

  const save = async (label: string, value: string, current: string | null) => {
    const ok = await run(() => setFicheEntry(building.building_id, {
      label, value: value.trim() || null, current_value: current,
    }).then(refresh));
    if (ok) { setEditing(null); setAdding(false); }
  };
  async function remove(label: string, current: string) {
    if (!window.confirm(t(lang, `Supprimer la ligne « ${label} » ?`, `Delete the “${label}” line?`))) return;
    await run(() => setFicheEntry(building.building_id, { label, value: null, current_value: current }).then(refresh));
  }

  return (
    <section className={`${styles.card} ${styles.cardWide}`} data-testid="building-fiche">
      <CardHead
        title={t(lang, 'Fiche technique', 'Technical sheet')}
        hint={t(lang, 'Accès, emplacements, codes et notes du bâtiment.', 'Access, locations, codes and notes.')}
        action={!adding && (
          <button type="button" className={styles.addBtn} data-testid="add-fiche"
                  onClick={() => { setError(null); setEditing(null); setAdding(true); }}>
            <PlusIcon size={14} /> {t(lang, 'Ajouter une ligne', 'Add a line')}
          </button>
        )}
      />
      {building.fiche.length > 8 && (
        <input type="search" className={`${styles.input} ${styles.ficheSearch}`} value={q}
               onChange={(e) => setQ(e.target.value)} data-testid="fiche-filter"
               placeholder={t(lang, 'Filtrer la fiche (p. ex. peinture, clé, eau)…', 'Filter the sheet (e.g. paint, key, water)…')}
               aria-label={t(lang, 'Filtrer la fiche technique', 'Filter the technical sheet')} />
      )}
      {adding && (
        <FicheForm lang={lang} label="" value="" fixedLabel={false} busy={busy} error={error}
                   onCancel={() => setAdding(false)}
                   onSave={(label, value) => save(label, value,
                     building.fiche.find((e) => e.label === label)?.value ?? null)} />
      )}
      {entries.length === 0 ? (
        <p className={styles.empty}>
          {q ? t(lang, 'Aucune ligne ne correspond.', 'No matching line.')
             : t(lang, 'La fiche technique est vide.', 'The technical sheet is empty.')}
        </p>
      ) : (
        <dl className={styles.fiche}>
          {entries.map((e) => (
            <div key={e.label} className={styles.ficheRow} data-testid="fiche-row">
              {editing === e.label ? (
                <FicheForm lang={lang} label={e.label} value={e.value} fixedLabel busy={busy} error={error}
                           onCancel={() => setEditing(null)}
                           onSave={(label, value) => save(label, value, e.value)} />
              ) : (
                <>
                  <dt>{e.label}</dt>
                  <dd>{e.value}</dd>
                  <div className={styles.rowTools}>
                    <IconButton label={t(lang, `Modifier « ${e.label} »`, `Edit “${e.label}”`)} testId="edit-fiche"
                                onClick={() => { setError(null); setAdding(false); setEditing(e.label); }}>
                      <PencilIcon />
                    </IconButton>
                    <IconButton label={t(lang, `Supprimer « ${e.label} »`, `Delete “${e.label}”`)} danger
                                onClick={() => remove(e.label, e.value)}>
                      <TrashIcon />
                    </IconButton>
                  </div>
                </>
              )}
            </div>
          ))}
        </dl>
      )}
      {error && editing === null && !adding && <p className={styles.error} role="alert">{error}</p>}
    </section>
  );
}

// ── Documents (files that still live in Drive or elsewhere) ──────────────────

function Documents({ building, lang }: { building: PortfolioBuildingDetail; lang: Lang }) {
  const refresh = useRefresh(building.building_id);
  const { busy, error, setError, run } = useSave(lang);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const ok = await run(() => createBuildingDocument(building.building_id, { title: title.trim(), url: url.trim() })
      .then(refresh));
    if (ok) { setAdding(false); setTitle(''); setUrl(''); }
  }
  async function remove(id: number, name: string) {
    if (!window.confirm(t(lang, `Retirer le lien « ${name} » ?`, `Remove the “${name}” link?`))) return;
    await run(() => deleteBuildingDocument(id).then(refresh));
  }

  return (
    <section className={`${styles.card} ${styles.cardWide}`} data-testid="building-documents">
      <CardHead
        title={t(lang, 'Documents', 'Documents')}
        hint={t(lang, 'Plans, contrats et autres fichiers (liens).', 'Plans, contracts and other files (links).')}
        action={!adding && (
          <button type="button" className={styles.addBtn} onClick={() => { setError(null); setAdding(true); }}>
            <PlusIcon size={14} /> {t(lang, 'Ajouter un lien', 'Add a link')}
          </button>
        )}
      />
      {adding && (
        <form className={styles.docForm} onSubmit={add}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t(lang, 'Titre', 'Title')}</span>
            <input className={styles.input} value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
          </label>
          <label className={`${styles.field} ${styles.fieldWide}`}>
            <span className={styles.fieldLabel}>{t(lang, 'Lien (https://…)', 'Link (https://…)')}</span>
            <input className={styles.input} type="url" value={url} onChange={(e) => setUrl(e.target.value)}
                   required pattern="https?://.+" />
          </label>
          {error && <p className={styles.error} role="alert">{error}</p>}
          <Actions lang={lang} busy={busy} onCancel={() => setAdding(false)} saveLabel={t(lang, 'Ajouter', 'Add')} />
        </form>
      )}
      {building.documents.length === 0 && !adding ? (
        <p className={styles.empty}>{t(lang, 'Aucun document lié.', 'No linked document.')}</p>
      ) : (
        <ul className={styles.docList}>
          {building.documents.map((d) => (
            <li key={d.document_id} className={styles.docRow}>
              {d.url
                ? <a href={d.url} target="_blank" rel="noreferrer" className={styles.docLink}>
                    {d.title ?? d.url} <LinkOutIcon />
                  </a>
                : <span>{d.title ?? '—'}</span>}
              <IconButton label={t(lang, 'Retirer', 'Remove')} danger
                          onClick={() => remove(d.document_id, d.title ?? d.url ?? '')}>
                <TrashIcon />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
      {error && !adding && <p className={styles.error} role="alert">{error}</p>}
    </section>
  );
}

export default function BuildingInfo({ building, lang }: { building: PortfolioBuildingDetail; lang: Lang }) {
  const { hash } = useLocation();
  // Search results link here with #fiche-technique.
  useEffect(() => {
    if (hash === '#fiche-technique') {
      document.getElementById('fiche-technique')?.scrollIntoView?.({ block: 'start' });
    }
  }, [hash]);

  return (
    <section id="fiche-technique" className={styles.wrap} aria-labelledby="building-info-title">
      <h2 id="building-info-title" className={styles.title}>{t(lang, 'Informations du bâtiment', 'Building information')}</h2>
      <div className={styles.grid}>
        <Characteristics building={building} lang={lang} />
        <Paint building={building} lang={lang} />
        <Fiche building={building} lang={lang} />
        <Documents building={building} lang={lang} />
      </div>
    </section>
  );
}
