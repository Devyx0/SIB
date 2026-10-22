import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  createManualRequest, fetchBuildings, fetchSectors, fetchUnitContext, fetchUnits, searchUnitNumbers,
} from '../../api/client';
import type { AccessChoice, AnimalsChoice, BuildingLookup, LeaseTenant, UnitByNumberLookup, UnitLookup, UnitNumberHit } from '../../api/client';
import type { SectorLookup } from '../../api/schema.d.ts';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { shrinkImage } from '../../lib/shrinkImage';
import { taxonomyElementOptions } from '../../lib/taxonomyElements';
import styles from './NouvelAppelModal.module.css';
import PhotoPicker, { type PickedPhoto } from '../../components/PhotoPicker';
import Select from '../../components/Select';

interface Props {
  open: boolean;
  onClose: () => void;
  lang?: Lang;
  /** Full page (receptionist) — no overlay / dismiss chrome. */
  asPage?: boolean;
}

function accessOptions(lang: Lang): { value: AccessChoice; label: string }[] {
  return [
    { value: 'yes', label: t(lang, 'Accès autorisé (traitement prioritaire)', 'Access granted (priority processing)') },
    { value: 'yes_instructions', label: t(lang, 'Accès autorisé : avec instructions précises (traitement prioritaire)', 'Access granted: with specific instructions (priority processing)') },
    { value: 'tenant_required', label: t(lang, 'Présence du locataire exigée (délai prolongé, non prioritaire)', 'Tenant presence required (extended delay, non-priority)') },
    { value: 'common_area', label: t(lang, 'N/A – espace commun', 'N/A – common area') },
  ];
}

export default function NouvelAppelModal({ open, onClose, lang = 'fr', asPage = false }: Props) {
  const qc = useQueryClient();

  const [callerName, setCallerName] = useState('');
  const [phone1, setPhone1] = useState('');
  const [phone2, setPhone2] = useState('');
  const [callerEmail, setCallerEmail] = useState('');
  const [callerEmailConfirm, setCallerEmailConfirm] = useState('');
  const [secondaryName, setSecondaryName] = useState('');
  const [secondaryEmail, setSecondaryEmail] = useState('');

  const [uniqueUnitNumber, setUniqueUnitNumber] = useState('');
  const [unitSuggestions, setUnitSuggestions] = useState<UnitNumberHit[]>([]);
  const [unitSuggestOpen, setUnitSuggestOpen] = useState(false);
  const [unitSuggestBusy, setUnitSuggestBusy] = useState(false);
  const [unitLookupMsg, setUnitLookupMsg] = useState<string | null>(null);
  const unitPickedRef = useRef<string | null>(null);
  const [leaseTenants, setLeaseTenants] = useState<LeaseTenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null);
  const [petsAllowed, setPetsAllowed] = useState(false);

  const [sectors, setSectors] = useState<SectorLookup[]>([]);
  const [sectorId, setSectorId] = useState<number | null>(null);
  const [buildings, setBuildings] = useState<BuildingLookup[]>([]);
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [units, setUnits] = useState<UnitLookup[]>([]);
  const [unitId, setUnitId] = useState<number | null>(null);
  const [unitsLoading, setUnitsLoading] = useState(false);
  const [unitsError, setUnitsError] = useState<string | null>(null);

  const [access, setAccess] = useState<AccessChoice>('yes');
  const [accessDetails, setAccessDetails] = useState('');
  const [animals, setAnimals] = useState<AnimalsChoice | null>(null);
  const [animalDetails, setAnimalDetails] = useState('');
  const [element, setElement] = useState('');
  const [symptome, setSymptome] = useState('');
  const [composante, setComposante] = useState('');
  const [emplacement, setEmplacement] = useState('');
  const [problem, setProblem] = useState('');
  const [attention, setAttention] = useState('');
  // Photos of the problem (recommended): files + local previews.
  const [photos, setPhotos] = useState<PickedPhoto[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setErrorMsg(null);
    fetchSectors()
      .then((list) => {
        setSectors(list);
        if (list.length === 1) setSectorId(list[0].sector_id);
        if (list.length === 0) {
          setErrorMsg(t(lang, 'Aucun secteur disponible.', 'No sectors available.'));
        }
      })
      .catch((err: unknown) => {
        setErrorMsg(err instanceof Error ? err.message : String(err));
      });
  }, [open, lang]);

  useEffect(() => {
    if (sectorId == null) {
      setBuildings([]);
      setBuildingId(null);
      return;
    }
    fetchBuildings(sectorId)
      .then((list) => { setBuildings(list); })
      .catch(() => setBuildings([]));
  }, [sectorId]);

  useEffect(() => {
    if (buildingId == null) {
      setUnits([]);
      setUnitsError(null);
      setUnitsLoading(false);
      return;
    }
    setUnitsError(null);
    setUnitsLoading(true);
    fetchUnits(buildingId)
      .then((list) => { setUnits(list); setUnitsLoading(false); })
      .catch(() => {
        setUnitsError(t(lang, 'Erreur lors du chargement des unités.', 'Error loading units.'));
        setUnitsLoading(false);
      });
  }, [buildingId, lang]);

  function resetPets() {
    setPetsAllowed(false);
    setAnimals(null);
    setAnimalDetails('');
  }

  function resetTenants() {
    setLeaseTenants([]);
    setSelectedTenantId(null);
  }

  function fillFromTenant(tn: LeaseTenant) {
    setSelectedTenantId(tn.tenant_id);
    if (tn.name) setCallerName(tn.name);
    if (tn.phone) setPhone1(tn.phone);
    if (tn.email) {
      setCallerEmail(tn.email);
      setCallerEmailConfirm(tn.email);
    } else {
      setCallerEmail('');
      setCallerEmailConfirm('');
    }
  }

  function reset() {
    setCallerName(''); setPhone1(''); setPhone2('');
    setCallerEmail(''); setCallerEmailConfirm('');
    setSecondaryName(''); setSecondaryEmail('');
    setUniqueUnitNumber('');
    unitPickedRef.current = null;
    setUnitSuggestions([]); setUnitSuggestOpen(false); setUnitSuggestBusy(false);
    setUnitLookupMsg(null);
    resetTenants();
    setSectors([]); setSectorId(null); setBuildings([]); setBuildingId(null);
    setUnits([]); setUnitId(null); setUnitsLoading(false); setUnitsError(null);
    setAccess('yes'); setAccessDetails('');
    resetPets();
    setElement(''); setSymptome(''); setComposante(''); setEmplacement('');
    setProblem(''); setAttention('');
    setPhotos((prev) => { prev.forEach((p) => URL.revokeObjectURL(p.url)); return []; });
    setSubmitting(false); setErrorMsg(null);
  }

  function handleClose() {
    reset();
    if (!asPage) onClose();
  }

  function clearCallerFields() {
    setCallerName('');
    setPhone1('');
    setPhone2('');
    setCallerEmail('');
    setCallerEmailConfirm('');
    setSelectedTenantId(null);
  }

  function applyLeaseContext(u: UnitByNumberLookup) {
    const tenants = u.tenants ?? [];
    setLeaseTenants(tenants);
    setPetsAllowed(u.pets_allowed);
    if (!u.pets_allowed) {
      setAnimals(null);
      setAnimalDetails('');
    }
    if (tenants.length === 1) {
      fillFromTenant(tenants[0]);
    } else if (tenants.length > 1) {
      // Wipe previous unit's tenant so the picker starts clean.
      clearCallerFields();
    } else {
      // Vacant / no lease: keep whatever was typed manually.
      setSelectedTenantId(null);
    }
  }

  async function applyUnitContext(u: UnitByNumberLookup) {
    setSectorId(u.sector_id);
    setBuildingId(u.building_id);
    setUnitId(u.unit_id);
    if (u.unique_unit_number) {
      unitPickedRef.current = u.unique_unit_number;
      setUniqueUnitNumber(u.unique_unit_number);
    }
    applyLeaseContext(u);
    const parts = [u.unique_unit_number].filter(Boolean) as string[];
    if (u.building_adresse) parts.push(u.building_adresse);
    if (u.numero_appartement) parts.push(u.numero_appartement);
    setUnitLookupMsg(parts.join(' — '));
  }

  async function onUnitPicked(nextUnitId: number | null) {
    setUnitId(nextUnitId);
    if (nextUnitId == null) {
      resetPets();
      resetTenants();
      return;
    }
    try {
      const u = await fetchUnitContext(nextUnitId);
      await applyUnitContext(u);
    } catch {
      resetPets();
      resetTenants();
    }
  }

  async function selectUnitHit(hit: UnitNumberHit) {
    unitPickedRef.current = hit.unique_unit_number;
    setUniqueUnitNumber(hit.unique_unit_number);
    setUnitSuggestions([]);
    setUnitSuggestOpen(false);
    setUnitLookupMsg(null);
    setErrorMsg(null);
    try {
      const u = await fetchUnitContext(hit.unit_id);
      await applyUnitContext(u);
    } catch (err: unknown) {
      resetPets();
      resetTenants();
      setUnitId(null);
      setUnitLookupMsg(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    if (!open) return;
    const q = uniqueUnitNumber.trim();
    if (q.length < 2 || q === unitPickedRef.current) {
      setUnitSuggestions([]);
      setUnitSuggestOpen(false);
      setUnitSuggestBusy(false);
      return;
    }
    let cancelled = false;
    setUnitSuggestBusy(true);
    const timer = window.setTimeout(() => {
      searchUnitNumbers(q)
        .then((hits) => {
          if (cancelled) return;
          setUnitSuggestions(hits);
          setUnitSuggestOpen(hits.length > 0);
        })
        .catch(() => {
          if (cancelled) return;
          setUnitSuggestions([]);
          setUnitSuggestOpen(false);
        })
        .finally(() => {
          if (!cancelled) setUnitSuggestBusy(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [uniqueUnitNumber, open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    if (!callerName.trim()) {
      setErrorMsg(t(lang, 'Nom requis.', 'Name required.'));
      return;
    }
    if (!phone1.trim()) {
      setErrorMsg(t(lang, 'Téléphone requis.', 'Phone required.'));
      return;
    }
    const email = callerEmail.trim();
    const emailConfirm = callerEmailConfirm.trim();
    if (email || emailConfirm) {
      if (!email) {
        setErrorMsg(t(lang, 'Courriel requis si confirmation fournie.', 'Email required when confirmation is filled.'));
        return;
      }
      if (email.toLowerCase() !== emailConfirm.toLowerCase()) {
        setErrorMsg(t(lang, 'Les courriels ne correspondent pas.', 'Emails do not match.'));
        return;
      }
    }
    if (buildingId == null) {
      setErrorMsg(t(lang, 'Sélectionnez un bâtiment.', 'Select a building.'));
      return;
    }
    if (unitId == null) {
      setErrorMsg(t(lang, 'Sélectionnez une unité valide dans la liste.', 'Select a valid unit from the list.'));
      return;
    }
    if (access === 'yes_instructions' && !accessDetails.trim()) {
      setErrorMsg(t(lang, "Précisions d'accès requises.", 'Access instructions required.'));
      return;
    }
    if (petsAllowed && animals == null) {
      setErrorMsg(t(lang, 'Indiquez si un animal est présent.', 'Say whether a pet is present.'));
      return;
    }
    if (!problem.trim()) {
      setErrorMsg(t(lang, 'Description du problème requise.', 'Problem description required.'));
      return;
    }
    if (!element.trim() || !symptome.trim() || !composante.trim() || !emplacement.trim()) {
      setErrorMsg(t(
        lang,
        'Taxonomie complète requise (élément, symptôme, composante, emplacement).',
        'Complete taxonomy required (element, symptom, component, location).',
      ));
      return;
    }
    setSubmitting(true);
    try {
      let encoded: Awaited<ReturnType<typeof shrinkImage>>[] = [];
      try {
        encoded = await Promise.all(photos.map((p) => shrinkImage(p.file)));
      } catch {
        setErrorMsg(t(lang, 'Une photo est illisible — retirez-la ou choisissez-en une autre.', 'A photo could not be read — remove it or pick another.'));
        return;
      }
      await createManualRequest({
        caller_name: callerName.trim(),
        phone_1: phone1.trim(),
        phone_2: phone2.trim() || undefined,
        caller_email: email || undefined,
        building_id: buildingId,
        unit_id: unitId,
        access,
        access_details: accessDetails.trim() || undefined,
        animals: petsAllowed && animals ? animals : undefined,
        animal_details: petsAllowed && animals === 'oui' ? (animalDetails.trim() || undefined) : undefined,
        element: element.trim(),
        symptome: symptome.trim(),
        composante: composante.trim(),
        emplacement: emplacement.trim(),
        secondary_name: secondaryName.trim() || undefined,
        secondary_email: secondaryEmail.trim() || undefined,
        problem: problem.trim(),
        attention: attention.trim() || undefined,
        ui_lang: lang,
        photos: encoded.length ? encoded : undefined,
      });
      qc.invalidateQueries({ queryKey: ['requests'] });
      handleClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    document.body.classList.add('modal-open');
    return () => { document.body.classList.remove('modal-open'); };
  }, [open]);

  const blockReasons: string[] = [];
  if (buildingId == null) {
    blockReasons.push(t(lang, 'Bâtiment requis.', 'Building required.'));
  }
  if (unitId == null) {
    blockReasons.push(t(lang, 'Unité valide requise (choisir dans la liste).', 'Valid unit required (pick from the list).'));
  }
  if (petsAllowed && animals == null) {
    blockReasons.push(t(lang, 'Indiquez si un animal est présent.', 'Say whether a pet is present.'));
  }
  if (access === 'yes_instructions' && !accessDetails.trim()) {
    blockReasons.push(t(lang, "Précisions d'accès requises.", 'Access instructions required.'));
  }
  if (!callerName.trim()) {
    blockReasons.push(t(lang, 'Nom requis.', 'Name required.'));
  }
  if (!phone1.trim()) {
    blockReasons.push(t(lang, 'Téléphone requis.', 'Phone required.'));
  }
  if (!problem.trim()) {
    blockReasons.push(t(lang, 'Description du problème requise.', 'Problem description required.'));
  }
  if (!element.trim() || !symptome.trim() || !composante.trim() || !emplacement.trim()) {
    blockReasons.push(t(
      lang,
      'Taxonomie complète requise (élément, symptôme, composante, emplacement).',
      'Complete taxonomy required (element, symptom, component, location).',
    ));
  }

  if (!open) return null;

  // The unique number was picked from the list and filled in the address.
  const autoFilled = unitId != null && uniqueUnitNumber.trim() !== ''
    && uniqueUnitNumber.trim() === unitPickedRef.current;

  // Footer chips show just the field ("Téléphone"), full sentence on hover.
  function shortReason(r: string): string {
    return r.replace(/\s*\b(requis|requise|requises|required)\b.*$/i, '').replace(/\.$/, '');
  }

  function unitOptionLabel(u: UnitLookup): string {
    const civic = u.rue ? u.rue.split(',')[0].trim() : null;
    return civic ? `${civic} – ${u.numero_appartement}` : u.numero_appartement;
  }

  return (
    <div
      className={asPage ? styles.page : styles.overlay}
      role={asPage ? undefined : 'dialog'}
      aria-modal={asPage ? undefined : true}
      aria-label={t(lang, 'Nouvel appel', 'New call')}
      data-testid={asPage ? 'nouvel-appel-page' : undefined}
    >
      <div className={asPage ? styles.pagePanel : styles.modal}>
        <div className={styles.headRow}>
          <div>
            <h2 className={styles.heading}>{t(lang, 'Nouvel appel', 'New call')}</h2>
            <p className={styles.subheading}>
              {t(lang, 'Saisissez la demande du locataire — les champs * sont requis.', 'Enter the tenant’s request — fields marked * are required.')}
            </p>
          </div>
          {!asPage && (
            <button
              type="button"
              className={styles.closeBtn}
              onClick={handleClose}
              aria-label={t(lang, 'Fermer', 'Close')}
              data-testid="nouvel-appel-close"
            >
              <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          )}
        </div>

        <form className={styles.modalForm} onSubmit={handleSubmit} noValidate>
          <div className={styles.formBody}>
          <div className={styles.grid}>
          <section className={`${styles.section} ${styles.areaUnit}`}>
            <header className={styles.sectionHead}>
              <span className={styles.stepNum} aria-hidden="true">1</span>
              <div>
                <h3 className={styles.sectionHeading}>{t(lang, 'Logement', 'Unit')}</h3>
                <p className={styles.sectionSub}>{t(lang, 'Par numéro unique, ou choisissez l’adresse.', 'By unique number, or pick the address.')}</p>
              </div>
            </header>
            <div className={styles.option}>
            <div className={styles.optionHead}>
              <span className={styles.optionTitle}>{t(lang, 'Numéro unique connu', 'Unique number known')}</span>
              <span className={styles.optionSub}>{t(lang, 'Remplit l’adresse et le locataire automatiquement', 'Fills in the address and tenant automatically')}</span>
            </div>
            <div className={styles.field}>
              <label htmlFor="unique-unit-number" className={styles.label}>
                {t(lang, "Numéro unique d'unité", 'Unique unit number')}
              </label>
              <div className={styles.suggestWrap}>
                <input
                  id="unique-unit-number"
                  className={styles.input}
                  role="combobox"
                  aria-expanded={unitSuggestOpen}
                  aria-autocomplete="list"
                  aria-controls="unique-unit-suggestions"
                  autoComplete="off"
                  placeholder={t(lang, 'Tapez pour chercher…', 'Type to search…')}
                  value={uniqueUnitNumber}
                  onChange={(e) => {
                    unitPickedRef.current = null;
                    setUniqueUnitNumber(e.target.value);
                    setUnitLookupMsg(null);
                  }}
                  onFocus={() => {
                    if (unitSuggestions.length > 0 && uniqueUnitNumber.trim() !== unitPickedRef.current) {
                      setUnitSuggestOpen(true);
                    }
                  }}
                  onBlur={() => {
                    // Delay so option click registers before list unmounts.
                    window.setTimeout(() => setUnitSuggestOpen(false), 150);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') setUnitSuggestOpen(false);
                  }}
                  data-testid="unique-unit-number"
                />
                {unitSuggestBusy && (
                  <p className={styles.hint}>{t(lang, 'Recherche…', 'Searching…')}</p>
                )}
                {unitSuggestOpen && unitSuggestions.length > 0 && (
                  <ul
                    id="unique-unit-suggestions"
                    className={styles.suggestList}
                    role="listbox"
                    data-testid="unique-unit-suggestions"
                  >
                    {unitSuggestions.map((hit) => (
                      <li key={hit.unit_id} role="option">
                        <button
                          type="button"
                          className={styles.suggestItem}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => void selectUnitHit(hit)}
                        >
                          {hit.unique_unit_number}
                          {(hit.building_adresse || hit.numero_appartement) && (
                            <span className={styles.suggestMeta}>
                              {[hit.building_adresse, hit.numero_appartement].filter(Boolean).join(' · ')}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            {unitLookupMsg && (
              <p className={autoFilled ? styles.lookupOk : styles.hint} data-testid="unit-lookup-msg">
                {autoFilled && <span aria-hidden="true">✓ </span>}{unitLookupMsg}
              </p>
            )}
            </div>

            <div className={styles.orDivider} role="separator" aria-label={t(lang, 'ou', 'or')}>
              <span>{t(lang, 'OU', 'OR')}</span>
            </div>

            <div className={`${styles.option} ${autoFilled ? styles.optionFilled : ''}`}>
            <div className={styles.optionHead}>
              <span className={styles.optionTitle}>
                {t(lang, 'Choisir l’adresse manuellement', 'Pick the address manually')}
                {autoFilled && (
                  <span className={styles.autoBadge} data-testid="address-autofilled">
                    {t(lang, 'Rempli automatiquement', 'Auto-filled')}
                  </span>
                )}
              </span>
              <span className={styles.optionSub}>{t(lang, 'Si le numéro unique n’est pas connu', 'If the unique number is not known')}</span>
            </div>
              <div className={styles.field}>
                <label htmlFor="picker-sector" className={styles.label}>
                  {t(lang, 'Secteur *', 'Sector *')}
                </label>
                <Select id="picker-sector" className={styles.select} value={sectorId ?? ''}
                  onChange={(e) => {
                    setSectorId(e.target.value ? Number(e.target.value) : null);
                    setBuildingId(null);
                    setUnitId(null);
                    resetPets();
                    resetTenants();
                  }}
                  data-testid="sector-select">
                  <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                  {sectors.map((s) => (
                    <option key={s.sector_id} value={s.sector_id}>{s.territoire}</option>
                  ))}
                </Select>
              </div>
              <div className={styles.field}>
                <label htmlFor="picker-building" className={styles.label}>
                  {t(lang, 'Bâtiment *', 'Building *')}
                </label>
                <Select id="picker-building" className={styles.select} value={buildingId ?? ''}
                  disabled={sectorId == null}
                  onChange={(e) => {
                    const bid = e.target.value ? Number(e.target.value) : null;
                    setBuildingId(bid);
                    setUnitId(null);
                    resetPets();
                    resetTenants();
                  }}
                  data-testid="building-select">
                  <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                  {buildings.map((b) => (
                    <option key={b.building_id} value={b.building_id}>
                      {b.adresse ?? b.web_building_name ?? String(b.building_id)}
                    </option>
                  ))}
                </Select>
              </div>
              {buildingId != null && (
                <div className={styles.field}>
                  <label htmlFor="picker-unit" className={styles.label}>
                    {t(lang, 'Unité (optionnel)', 'Unit (optional)')}
                  </label>
                  {unitsLoading
                    ? <p className={styles.hint}>{t(lang, 'Chargement…', 'Loading…')}</p>
                    : !unitsError && units.length === 0
                      ? <p className={styles.hint} data-testid="no-units-msg">
                          {t(lang, 'Aucune unité enregistrée pour ce bâtiment', 'No units registered for this building')}
                        </p>
                      : (
                        <Select id="picker-unit" className={styles.select} value={unitId ?? ''}
                          onChange={(e) => {
                            void onUnitPicked(e.target.value ? Number(e.target.value) : null);
                          }}
                          data-testid="unit-select">
                          <option value="">— {t(lang, 'Aucune', 'None')} —</option>
                          {units.map((u) => (
                            <option key={u.unit_id} value={u.unit_id}>{unitOptionLabel(u)}</option>
                          ))}
                        </Select>
                      )
                  }
                </div>
              )}
            </div>
          </section>

          <section className={`${styles.section} ${styles.areaCaller}`}>
            <header className={styles.sectionHead}>
              <span className={styles.stepNum} aria-hidden="true">2</span>
              <div>
                <h3 className={styles.sectionHeading}>{t(lang, 'Appelant', 'Caller')}</h3>
                <p className={styles.sectionSub}>{t(lang, 'Qui appelle et comment le joindre.', 'Who is calling and how to reach them.')}</p>
              </div>
            </header>
            {leaseTenants.length > 1 && (
              <div className={styles.field}>
                <label htmlFor="tenant-select" className={styles.label}>
                  {t(lang, 'Locataire *', 'Tenant *')}
                </label>
                <Select
                  id="tenant-select"
                  className={styles.select}
                  value={selectedTenantId ?? ''}
                  onChange={(e) => {
                    const id = e.target.value ? Number(e.target.value) : null;
                    const tn = leaseTenants.find((x) => x.tenant_id === id);
                    if (tn) fillFromTenant(tn);
                    else setSelectedTenantId(null);
                  }}
                  data-testid="tenant-select"
                >
                  <option value="">— {t(lang, 'Choisir le locataire', 'Choose tenant')} —</option>
                  {leaseTenants.map((tn) => (
                    <option key={tn.tenant_id} value={tn.tenant_id}>
                      {tn.name ?? `#${tn.tenant_id}`}
                      {tn.phone ? ` — ${tn.phone}` : ''}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <div className={styles.field}>
              <label htmlFor="caller-name" className={styles.label}>{t(lang, 'Nom *', 'Name *')}</label>
              <input id="caller-name" className={styles.input} value={callerName}
                onChange={(e) => setCallerName(e.target.value)} data-testid="caller-name" required />
            </div>
            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="caller-email" className={styles.label}>{t(lang, 'Courriel', 'Email')}</label>
                <input id="caller-email" className={styles.input} type="email" value={callerEmail}
                  onChange={(e) => setCallerEmail(e.target.value)}
                  placeholder={t(lang, 'Adresse courriel', 'Email address')}
                  data-testid="caller-email" />
              </div>
              <div className={styles.field}>
                <label htmlFor="caller-email-confirm" className={styles.label}>
                  {t(lang, 'Confirmer le courriel', 'Confirm email')}
                </label>
                <input id="caller-email-confirm" className={styles.input} type="email" value={callerEmailConfirm}
                  onChange={(e) => setCallerEmailConfirm(e.target.value)}
                  placeholder={t(lang, 'Confirmer le courriel', 'Confirm email')}
                  data-testid="caller-email-confirm" />
              </div>
            </div>
            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="phone-1" className={styles.label}>{t(lang, 'Téléphone 1 *', 'Phone 1 *')}</label>
                <input id="phone-1" className={styles.input} value={phone1}
                  onChange={(e) => setPhone1(e.target.value)}
                  placeholder="(999) 999-9999" data-testid="phone-1" required />
              </div>
              <div className={styles.field}>
                <label htmlFor="phone-2" className={styles.label}>{t(lang, 'Téléphone 2', 'Phone 2')}</label>
                <input id="phone-2" className={styles.input} value={phone2}
                  onChange={(e) => setPhone2(e.target.value)}
                  placeholder="(999) 999-9999" data-testid="phone-2" />
              </div>
            </div>
            <details className={styles.disclosure} open={Boolean(secondaryName || secondaryEmail) || undefined}>
              <summary>{t(lang, '+ Autre personne à contacter (optionnel)', '+ Another contact person (optional)')}</summary>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label htmlFor="secondary-name" className={styles.label}>
                    {t(lang, 'Autre personne à contacter', 'Other person to contact')}
                  </label>
                  <input id="secondary-name" className={styles.input} value={secondaryName}
                    onChange={(e) => setSecondaryName(e.target.value)} data-testid="secondary-name" />
                </div>
                <div className={styles.field}>
                  <label htmlFor="secondary-email" className={styles.label}>
                    {t(lang, 'Courriel 2e personne', '2nd person email')}
                  </label>
                  <input id="secondary-email" className={styles.input} type="email" value={secondaryEmail}
                    onChange={(e) => setSecondaryEmail(e.target.value)} data-testid="secondary-email" />
                </div>
              </div>
            </details>
          </section>

          <section className={`${styles.section} ${styles.areaAccess}`}>
            <header className={styles.sectionHead}>
              <span className={styles.stepNum} aria-hidden="true">3</span>
              <div>
                <h3 className={styles.sectionHeading}>{t(lang, 'Accès', 'Access')}</h3>
                <p className={styles.sectionSub}>{t(lang, 'Entrée et animaux.', 'Entry and pets.')}</p>
              </div>
            </header>
            <fieldset className={styles.fieldset}>
              <legend className={styles.label}>{t(lang, 'Accès au logement *', 'Unit access *')}</legend>
              <div className={styles.radioGroup} data-testid="access-group">
                {accessOptions(lang).map((o) => (
                  <label key={o.value} className={styles.radioRow}>
                    <input type="radio" name="access" value={o.value}
                      checked={access === o.value}
                      onChange={() => setAccess(o.value)} />
                    <span>{o.label}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            {access === 'yes_instructions' && (
              <div className={styles.field}>
                <label htmlFor="access-details" className={styles.label}>
                  {t(lang, 'Instructions d\'accès *', 'Access instructions *')}
                </label>
                <input id="access-details" className={styles.input} value={accessDetails}
                  onChange={(e) => setAccessDetails(e.target.value)} data-testid="access-details" />
              </div>
            )}
            {petsAllowed && (
              <>
                <fieldset className={styles.fieldset}>
                  <legend className={styles.label}>
                    {t(lang, 'Animal présent *', 'Pet present *')}
                  </legend>
                  <div className={styles.radioGroupInline} data-testid="animals-group">
                    {([
                      { value: 'oui' as const, label: t(lang, 'Oui', 'Yes') },
                      { value: 'non' as const, label: t(lang, 'Non', 'No') },
                    ]).map((o) => (
                      <label key={o.value} className={styles.radioRow}>
                        <input type="radio" name="animals" value={o.value}
                          checked={animals === o.value}
                          onChange={() => setAnimals(o.value)} />
                        <span>{o.label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                {animals === 'oui' && (
                  <div className={styles.field}>
                    <label htmlFor="animal-details" className={styles.label}>
                      {t(lang, "Type d'animaux", 'Animal type')}
                    </label>
                    <input id="animal-details" className={styles.input} value={animalDetails}
                      onChange={(e) => setAnimalDetails(e.target.value)} data-testid="animal-details" />
                  </div>
                )}
              </>
            )}
          </section>

          <section className={`${styles.section} ${styles.areaProblem}`}>
            <header className={styles.sectionHead}>
              <span className={styles.stepNum} aria-hidden="true">4</span>
              <div>
                <h3 className={styles.sectionHeading}>{t(lang, 'Problème', 'Problem')}</h3>
                <p className={styles.sectionSub}>{t(lang, 'Classification et description.', 'Classification and description.')}</p>
              </div>
            </header>
            <div className={styles.taxonomy}>
            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="element" className={styles.label}>{t(lang, 'Élément', 'Element')}</label>
                <Select
                  id="element"
                  className={styles.select}
                  value={element}
                  onChange={(e) => setElement(e.target.value)}
                  data-testid="element"
                >
                  <option value="">{t(lang, 'Choisir…', 'Choose…')}</option>
                  {taxonomyElementOptions(lang).map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </Select>
              </div>
              <div className={styles.field}>
                <label htmlFor="symptome" className={styles.label}>{t(lang, 'Symptôme', 'Symptom')}</label>
                <input id="symptome" className={styles.input} value={symptome}
                  onChange={(e) => setSymptome(e.target.value)} data-testid="symptome" />
              </div>
            </div>
            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="composante" className={styles.label}>{t(lang, 'Composante', 'Component')}</label>
                <input id="composante" className={styles.input} value={composante}
                  onChange={(e) => setComposante(e.target.value)} data-testid="composante" />
              </div>
              <div className={styles.field}>
                <label htmlFor="emplacement" className={styles.label}>{t(lang, 'Emplacement', 'Location')}</label>
                <input id="emplacement" className={styles.input} value={emplacement}
                  onChange={(e) => setEmplacement(e.target.value)} data-testid="emplacement" />
              </div>
            </div>
            </div>
            <div className={styles.field}>
              <label htmlFor="problem" className={styles.label}>
                {t(lang, 'Description du problème *', 'Problem description *')}
              </label>
              <textarea id="problem" className={styles.textarea} value={problem}
                onChange={(e) => setProblem(e.target.value)} data-testid="problem" rows={3} required />
            </div>
            <div className={styles.field} data-testid="photo-field">
              <span className={styles.label} id="intake-photos-label">
                {t(lang, 'Photos du problème', 'Photos of the problem')}
                <span className={styles.recommended}>{t(lang, 'Recommandé', 'Recommended')}</span>
              </span>
              <p className={styles.hint}>
                {t(lang,
                  'Aide le technicien à préparer sa visite. Jusqu’à 5 photos.',
                  'Helps the technician prepare. Up to 5 photos.')}
              </p>
              <PhotoPicker lang={lang} photos={photos} onChange={setPhotos} labelledBy="intake-photos-label" />
            </div>
            <div className={`${styles.field} ${styles.attentionField}`}>
              <label htmlFor="attention" className={styles.label}>
                <span aria-hidden="true">⚠</span> ATTENTION{' '}
                <span className={styles.labelHint}>{t(lang, '— note visible par le technicien', '— note shown to the technician')}</span>
              </label>
              <input id="attention" className={styles.input} value={attention}
                onChange={(e) => setAttention(e.target.value)} />
            </div>
          </section>
          </div>
          </div>

          <footer className={styles.footer}>
          {unitsError && <p className={styles.errorMsg} data-testid="units-error">{unitsError}</p>}
          {errorMsg && <p className={styles.errorMsg} data-testid="error-msg">{errorMsg}</p>}
          <div className={styles.footerRow}>
          {blockReasons.length > 0 ? (
            <div className={styles.status}>
              <span className={styles.statusLabel}>
                {t(lang, `À compléter (${blockReasons.length})`, `To complete (${blockReasons.length})`)}
              </span>
              <ul className={styles.blockReasons} data-testid="block-reasons">
                {blockReasons.map((r) => (
                  <li key={r} title={r}>{shortReason(r)}</li>
                ))}
              </ul>
            </div>
          ) : (
            <span className={styles.ready}>{t(lang, '✓ Prêt à créer', '✓ Ready to create')}</span>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={handleClose}>
              {asPage
                ? t(lang, 'Effacer', 'Clear')
                : t(lang, 'Annuler', 'Cancel')}
            </button>
            <button type="submit" className={styles.submitBtn}
              disabled={submitting || blockReasons.length > 0}
              data-testid="submit-btn">
              {submitting
                ? t(lang, 'Création…', 'Creating…')
                : t(lang, 'Créer l’appel', 'Create call')}
            </button>
          </div>
          </div>
          </footer>
        </form>
      </div>
    </div>
  );
}
