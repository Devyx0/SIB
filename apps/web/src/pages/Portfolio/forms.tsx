import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  createBuilding, createProject, createUnit, fetchPortfolioBuilding, updateBuilding, updateProject, updateUnit,
} from '../../api/client';
import type { BuildingFields, ProjectFields, UnitFields } from '../../api/client';
import FormDialog, { Field, FieldGroup, inputClass } from '../../components/FormDialog';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { diff, errorText, isEmptyPatch } from './editing';
import { portfolioPath } from './shared';

// Add / edit dialogs for each level of the hierarchy. Create dialogs open the
// new item when saved; edit dialogs stay where they are.

type Text = string | null | undefined;
const v = (s: Text) => s ?? '';

export function useSubmit(lang: Lang, onDone: () => void) {
  const qc = useQueryClient();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run<T>(fn: () => Promise<T>, after?: (r: T) => void) {
    setSubmitting(true);
    setError(null);
    try {
      const result = await fn();
      await qc.invalidateQueries({ queryKey: ['portfolio'] });
      onDone();
      after?.(result);
    } catch (err) {
      setError(errorText(err, lang));
    } finally {
      setSubmitting(false);
    }
  }
  return { submitting, error, setError, run };
}

// ── Project ──────────────────────────────────────────────────────────────────

type ProjectFormProps = {
  lang: Lang;
  onClose: () => void;
} & (
  | { mode: 'create'; sectorId: number }
  | { mode: 'edit'; projectId: number; initial: ProjectFields }
);

export function ProjectDialog(props: ProjectFormProps) {
  const { lang, onClose } = props;
  const navigate = useNavigate();
  const { submitting, error, run } = useSubmit(lang, onClose);
  const initial: ProjectFields = props.mode === 'edit'
    ? props.initial : { nom_unique_projet: null, adresse_quickbooks: null, accounting_project_number: null };
  const [draft, setDraft] = useState(initial);
  const [building, setBuilding] = useState({ adresse: '', ville: '', code_postal: '' });
  const set = (k: keyof ProjectFields) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));

  function submit() {
    if (props.mode === 'create') {
      const sectorId = props.sectorId;
      run(() => createProject({
        nom_unique_projet: v(draft.nom_unique_projet).trim(),
        adresse_quickbooks: draft.adresse_quickbooks,
        accounting_project_number: draft.accounting_project_number,
        first_building: { sector_id: sectorId, ...building },
      }), (r) => r.project_id && navigate(portfolioPath.project(sectorId, r.project_id)));
    } else {
      const patch = diff(initial, draft);
      if (isEmptyPatch(patch)) { onClose(); return; }
      const projectId = props.projectId;
      run(() => updateProject(projectId, patch));
    }
  }

  return (
    <FormDialog
      lang={lang}
      testId="project-dialog"
      eyebrow={t(lang, 'Projet', 'Project')}
      title={props.mode === 'create' ? t(lang, 'Nouveau projet', 'New project') : t(lang, 'Modifier le projet', 'Edit project')}
      submitLabel={props.mode === 'create' ? t(lang, 'Créer le projet', 'Create project') : undefined}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'Nom du projet *', 'Project name *')} wide>
          <input className={inputClass} value={v(draft.nom_unique_projet)} onChange={set('nom_unique_projet')}
                 required maxLength={200} name="nom_unique_projet" />
        </Field>
        <Field label={t(lang, 'Adresse (QuickBooks)', 'Address (QuickBooks)')}>
          <input className={inputClass} value={v(draft.adresse_quickbooks)} onChange={set('adresse_quickbooks')}
                 maxLength={300} />
        </Field>
        <Field label={t(lang, 'No comptable', 'Accounting no.')}>
          <input className={inputClass} value={v(draft.accounting_project_number)}
                 onChange={set('accounting_project_number')} maxLength={50} />
        </Field>
      </FieldGroup>
      {props.mode === 'create' && (
        <FieldGroup title={t(lang, 'Premier bâtiment', 'First building')}>
          <Field label={t(lang, 'Adresse *', 'Address *')} wide
                 hint={t(lang, 'Un projet est rattaché au secteur par ses bâtiments.',
                               'A project belongs to the sector through its buildings.')}>
            <input className={inputClass} value={building.adresse} required maxLength={300} name="first_adresse"
                   onChange={(e) => setBuilding((b) => ({ ...b, adresse: e.target.value }))} />
          </Field>
          <Field label={t(lang, 'Ville', 'City')}>
            <input className={inputClass} value={building.ville} maxLength={100}
                   onChange={(e) => setBuilding((b) => ({ ...b, ville: e.target.value }))} />
          </Field>
          <Field label={t(lang, 'Code postal', 'Postal code')}>
            <input className={inputClass} value={building.code_postal} maxLength={20}
                   onChange={(e) => setBuilding((b) => ({ ...b, code_postal: e.target.value }))} />
          </Field>
        </FieldGroup>
      )}
    </FormDialog>
  );
}

// ── Building ─────────────────────────────────────────────────────────────────

type BuildingDraft = Required<Pick<BuildingFields,
  'adresse' | 'ville' | 'code_postal' | 'web_building_name' | 'actif_inactif'
  | 'nb_logements' | 'nb_etages' | 'annee_construction'>>;

const EMPTY_BUILDING: BuildingDraft = {
  adresse: null, ville: null, code_postal: null, web_building_name: null, actif_inactif: 'Actif',
  nb_logements: null, nb_etages: null, annee_construction: null,
};

function BuildingFieldsForm({ draft, setDraft, lang }: {
  draft: BuildingDraft; setDraft: (f: (d: BuildingDraft) => BuildingDraft) => void; lang: Lang;
}) {
  const set = (k: keyof BuildingDraft) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));
  return (
    <FieldGroup>
      <Field label={t(lang, 'Adresse *', 'Address *')} wide>
        <input className={inputClass} value={v(draft.adresse)} onChange={set('adresse')} required maxLength={300}
               name="adresse" />
      </Field>
      <Field label={t(lang, 'Ville', 'City')}>
        <input className={inputClass} value={v(draft.ville)} onChange={set('ville')} maxLength={100} />
      </Field>
      <Field label={t(lang, 'Code postal', 'Postal code')}>
        <input className={inputClass} value={v(draft.code_postal)} onChange={set('code_postal')} maxLength={20} />
      </Field>
      <Field label={t(lang, 'Nom (site web)', 'Name (website)')}>
        <input className={inputClass} value={v(draft.web_building_name)} onChange={set('web_building_name')}
               maxLength={200} />
      </Field>
      <Field label={t(lang, 'Statut', 'Status')}>
        <Select className={inputClass} value={draft.actif_inactif ?? ''}
                aria-label={t(lang, 'Statut', 'Status')}
                onChange={(e) => setDraft((d) => ({ ...d, actif_inactif: (e.target.value || null) as BuildingDraft['actif_inactif'] }))}>
          <option value="Actif">{t(lang, 'Actif', 'Active')}</option>
          <option value="Inactif">{t(lang, 'Inactif', 'Inactive')}</option>
        </Select>
      </Field>
      <Field label={t(lang, 'Logements', 'Units')}>
        <input className={inputClass} value={v(draft.nb_logements)} onChange={set('nb_logements')} maxLength={20}
               inputMode="numeric" />
      </Field>
      <Field label={t(lang, 'Étages', 'Floors')}>
        <input className={inputClass} value={v(draft.nb_etages)} onChange={set('nb_etages')} maxLength={20}
               inputMode="numeric" />
      </Field>
      <Field label={t(lang, 'Année de construction', 'Year built')}>
        <input className={inputClass} value={v(draft.annee_construction)} onChange={set('annee_construction')}
               maxLength={50} />
      </Field>
    </FieldGroup>
  );
}

type BuildingFormProps = {
  lang: Lang;
  onClose: () => void;
} & (
  | { mode: 'create'; projectId: number; sectorId: number }
  | { mode: 'edit'; buildingId: number }
);

export function BuildingDialog(props: BuildingFormProps) {
  const { lang, onClose } = props;
  const navigate = useNavigate();
  const { submitting, error, run } = useSubmit(lang, onClose);
  const editId = props.mode === 'edit' ? props.buildingId : null;
  // The card only carries a summary; the edit form loads the whole building.
  const { data: building, isLoading } = useQuery({
    queryKey: ['portfolio', 'building', editId],
    queryFn: () => fetchPortfolioBuilding(editId as number),
    enabled: editId != null,
  });
  const initial: BuildingDraft = building ? {
    adresse: building.adresse, ville: building.ville, code_postal: building.code_postal,
    web_building_name: building.web_building_name,
    actif_inactif: (building.actif_inactif as BuildingDraft['actif_inactif']) ?? null,
    nb_logements: building.nb_logements, nb_etages: building.nb_etages,
    annee_construction: building.annee_construction,
  } : EMPTY_BUILDING;
  const [draft, setDraft] = useState<BuildingDraft | null>(props.mode === 'create' ? EMPTY_BUILDING : null);
  const current = draft ?? (building ? initial : null);

  function submit() {
    if (!current) return;
    if (props.mode === 'create') {
      const { projectId, sectorId } = props;
      run(() => createBuilding({ ...current, adresse: v(current.adresse).trim(), project_id: projectId, sector_id: sectorId }),
          (r) => r.building_id && navigate(portfolioPath.building(r.building_id)));
    } else {
      const patch = diff(initial, current);
      if (isEmptyPatch(patch)) { onClose(); return; }
      run(() => updateBuilding(props.buildingId, patch));
    }
  }

  return (
    <FormDialog
      lang={lang}
      testId="building-dialog"
      eyebrow={t(lang, 'Bâtiment', 'Building')}
      title={props.mode === 'create' ? t(lang, 'Nouveau bâtiment', 'New building') : t(lang, 'Modifier le bâtiment', 'Edit building')}
      submitLabel={props.mode === 'create' ? t(lang, 'Créer le bâtiment', 'Create building') : undefined}
      submitting={submitting || (props.mode === 'edit' && isLoading)}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      {current
        ? <BuildingFieldsForm draft={current} lang={lang}
                              setDraft={(f) => setDraft(f(current))} />
        : <p>{t(lang, 'Chargement…', 'Loading…')}</p>}
    </FormDialog>
  );
}

// ── Unit ─────────────────────────────────────────────────────────────────────

type UnitFormProps = {
  lang: Lang;
  onClose: () => void;
} & (
  | { mode: 'create'; buildingId: number; defaultRue?: string | null }
  | { mode: 'edit'; unitId: number; initial: UnitFields }
);

export function UnitDialog(props: UnitFormProps) {
  const { lang, onClose } = props;
  const navigate = useNavigate();
  const { submitting, error, run } = useSubmit(lang, onClose);
  const initial: UnitFields = props.mode === 'edit'
    ? props.initial
    : { numero_appartement: null, rue: props.defaultRue ?? null, grandeur: null, unique_unit_number: null };
  const [draft, setDraft] = useState(initial);
  const set = (k: keyof UnitFields) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));

  function submit() {
    if (props.mode === 'create') {
      const { buildingId } = props;
      run(() => createUnit({ ...draft, numero_appartement: v(draft.numero_appartement).trim(), building_id: buildingId }),
          (r) => r.unit_id && navigate(portfolioPath.unit(r.unit_id)));
    } else {
      const patch = diff(initial, draft);
      if (isEmptyPatch(patch)) { onClose(); return; }
      run(() => updateUnit(props.unitId, patch));
    }
  }

  return (
    <FormDialog
      lang={lang}
      testId="unit-dialog"
      eyebrow={t(lang, 'Logement', 'Unit')}
      title={props.mode === 'create' ? t(lang, 'Nouveau logement', 'New unit') : t(lang, 'Modifier le logement', 'Edit unit')}
      submitLabel={props.mode === 'create' ? t(lang, 'Créer le logement', 'Create unit') : undefined}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onClose={onClose}
    >
      <FieldGroup>
        <Field label={t(lang, 'No de logement *', 'Unit no. *')}>
          <input className={inputClass} value={v(draft.numero_appartement)} onChange={set('numero_appartement')}
                 required maxLength={50} name="numero_appartement" />
        </Field>
        <Field label={t(lang, 'Grandeur', 'Size')} hint={t(lang, 'p. ex. 4 1/2', 'e.g. 4 1/2')}>
          <input className={inputClass} value={v(draft.grandeur)} onChange={set('grandeur')} maxLength={50} />
        </Field>
        <Field label={t(lang, 'Adresse du logement', 'Unit address')} wide>
          <input className={inputClass} value={v(draft.rue)} onChange={set('rue')} maxLength={300} />
        </Field>
        <Field label={t(lang, 'Numéro unique', 'Unique number')} wide
               hint={t(lang, 'Identifiant utilisé par les appels (p. ex. 846-315 Sainte-Foy).',
                             'Identifier used by calls (e.g. 846-315 Sainte-Foy).')}>
          <input className={inputClass} value={v(draft.unique_unit_number)} onChange={set('unique_unit_number')}
                 maxLength={100} />
        </Field>
      </FieldGroup>
    </FormDialog>
  );
}
