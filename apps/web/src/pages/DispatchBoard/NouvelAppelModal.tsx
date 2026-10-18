import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  createManualRequest, fetchBuildings, fetchSectors, fetchUnits, matchAddress,
} from '../../api/client';
import type { AnimalsChoice, BuildingLookup, MatchAddressResponse, UnitLookup } from '../../api/client';
import type { SectorLookup } from '../../api/schema.d.ts';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './NouvelAppelModal.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
  lang?: Lang;
}

const ACCESS_OPTIONS = [
  { value: 'yes',             label: 'Accès autorisé (traitement prioritaire)' },
  { value: 'tenant_required', label: 'Présence du locataire exigée' },
  { value: 'common_area',     label: 'N/A – espace commun' },
  { value: 'unknown',         label: 'Accès non précisé' },
] as const;

const ANIMALS_OPTIONS: { value: AnimalsChoice; label: string }[] = [
  { value: 'non', label: 'Non' },
  { value: 'oui', label: 'Oui' },
  { value: 'na',  label: 'N/A espace commun' },
];

const MATCH_STATUS_LABELS: Record<string, string> = {
  exact:         'Adresse trouvée exactement',
  building_only: 'Bâtiment trouvé (unité non identifiée)',
  ambiguous:     'Plusieurs bâtiments correspondent',
  no_match:      'Adresse introuvable — sélectionner manuellement',
  garbled:       'Adresse illisible — sélectionner manuellement',
};

const MATCH_STATUS_STYLE: Record<string, string> = {
  exact:         styles.matchOk,
  building_only: styles.matchOk,
  ambiguous:     styles.matchWarn,
  no_match:      styles.matchError,
  garbled:       styles.matchError,
};

type Phase = 'form' | 'confirm';

export default function NouvelAppelModal({ open, onClose, lang = 'fr' }: Props) {
  const qc = useQueryClient();
  const [phase, setPhase] = useState<Phase>('form');

  // ── Caller ─────────────────────────────────────────────────────────────
  const [callerName, setCallerName] = useState('');
  const [phone1, setPhone1] = useState('');
  const [callerEmail, setCallerEmail] = useState('');

  // ── Address ─────────────────────────────────────────────────────────────
  const [civic, setCivic] = useState('');
  const [street, setStreet] = useState('');
  const [apartment, setApartment] = useState('');
  const [city, setCity] = useState('Québec');

  // ── Problem ─────────────────────────────────────────────────────────────
  const [access, setAccess] = useState<'yes' | 'tenant_required' | 'common_area' | 'unknown'>('yes');
  const [accessDetails, setAccessDetails] = useState('');
  const [animals, setAnimals] = useState<AnimalsChoice>('non');
  const [animalDetails, setAnimalDetails] = useState('');
  const [problem, setProblem] = useState('');
  const [attention, setAttention] = useState('');

  // ── Confirm-phase state ─────────────────────────────────────────────────
  const [matchResult, setMatchResult] = useState<MatchAddressResponse | null>(null);
  const [confirmBuildingId, setConfirmBuildingId] = useState<number | null>(null);
  const [confirmUnitId, setConfirmUnitId] = useState<number | null>(null);
  const [confirmUnits, setConfirmUnits] = useState<UnitLookup[]>([]);

  // Full sector/building picker for no_match / garbled
  const [sectors, setSectors] = useState<SectorLookup[]>([]);
  const [pickerSectorId, setPickerSectorId] = useState<number | null>(null);
  const [pickerBuildings, setPickerBuildings] = useState<BuildingLookup[]>([]);

  // ── Status ──────────────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [unitsError, setUnitsError] = useState<string | null>(null);

  // Load units when confirm building changes — unit reset is handled by picker onChange, not here,
  // so an exact-match pre-population of confirmUnitId is not wiped.
  useEffect(() => {
    if (confirmBuildingId != null) {
      setUnitsError(null);
      fetchUnits(confirmBuildingId)
        .then(setConfirmUnits)
        .catch(() => setUnitsError(t(lang, 'Erreur lors du chargement des unités.', 'Error loading units.')));
    } else {
      setConfirmUnits([]);
      setUnitsError(null);
    }
  }, [confirmBuildingId, lang]);

  // Lazily load sectors when the no_match/garbled picker becomes visible
  useEffect(() => {
    const needsPicker =
      matchResult?.match_status === 'no_match' || matchResult?.match_status === 'garbled';
    if (phase === 'confirm' && needsPicker && sectors.length === 0) {
      fetchSectors().then(setSectors).catch(() => {});
    }
  }, [phase, matchResult, sectors.length]);

  // Load buildings for the selected sector
  useEffect(() => {
    if (pickerSectorId != null) {
      fetchBuildings(pickerSectorId).then(setPickerBuildings).catch(() => {});
      setConfirmBuildingId(null);
    }
  }, [pickerSectorId]);

  function reset() {
    setPhase('form');
    setCallerName(''); setPhone1(''); setCallerEmail('');
    setCivic(''); setStreet(''); setApartment(''); setCity('Québec');
    setAccess('yes'); setAccessDetails('');
    setAnimals('non'); setAnimalDetails('');
    setProblem(''); setAttention('');
    setMatchResult(null);
    setConfirmBuildingId(null); setConfirmUnitId(null); setConfirmUnits([]);
    setSectors([]); setPickerSectorId(null); setPickerBuildings([]);
    setSubmitting(false); setErrorMsg(null);
  }

  function handleClose() { reset(); onClose(); }

  // ── Step 1: match address (no DB write) ──────────────────────────────────
  async function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    if (!callerName.trim()) { setErrorMsg(t(lang, 'Nom requis.', 'Name required.')); return; }
    if (!civic.trim() || !street.trim()) {
      setErrorMsg(t(lang, 'Numéro civique et rue requis.', 'Civic number and street required.'));
      return;
    }
    if (!problem.trim()) {
      setErrorMsg(t(lang, 'Description du problème requise.', 'Problem description required.'));
      return;
    }
    setSubmitting(true);
    try {
      const result = await matchAddress({
        civic: civic.trim(),
        street: street.trim(),
        apartment: apartment.trim() || undefined,
      });
      setMatchResult(result);
      if (result.match_status === 'exact') {
        setConfirmBuildingId(result.building_id);
        setConfirmUnitId(result.unit_id);
      } else if (result.match_status === 'building_only') {
        setConfirmBuildingId(result.building_id);
      } else {
        setConfirmBuildingId(null);
      }
      setPhase('confirm');
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  // ── Step 2: create (one DB write) ────────────────────────────────────────
  async function handleConfirm() {
    if (!confirmBuildingId) {
      setErrorMsg(t(lang, 'Sélectionnez un bâtiment.', 'Select a building.'));
      return;
    }
    setSubmitting(true);
    setErrorMsg(null);
    try {
      await createManualRequest({
        caller_name: callerName.trim(),
        phone_1: phone1.trim() || undefined,
        caller_email: callerEmail.trim() || undefined,
        civic: civic.trim(),
        street: street.trim(),
        apartment: apartment.trim() || undefined,
        city: city.trim() || 'Québec',
        access,
        access_details: accessDetails.trim() || undefined,
        animals,
        animal_details: animals === 'oui' ? (animalDetails.trim() || undefined) : undefined,
        problem: problem.trim(),
        attention: attention.trim() || undefined,
        building_id_override: confirmBuildingId,
        unit_id_override: confirmUnitId ?? undefined,
      });
      qc.invalidateQueries({ queryKey: ['requests'] });
      handleClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  const unitLabel = (() => {
    const u = confirmUnits.find((u) => u.unit_id === confirmUnitId);
    if (!u) return undefined;
    const civic = u.rue ? u.rue.split(',')[0].trim() : null;
    return civic ? `${u.numero_appartement} (${civic})` : u.numero_appartement;
  })();

  function unitOptionLabel(u: UnitLookup): string {
    const civic = u.rue ? u.rue.split(',')[0].trim() : null;
    return civic ? `${u.numero_appartement} (${civic})` : u.numero_appartement;
  }

  return (
    <div className={styles.overlay} role="dialog" aria-modal aria-label={t(lang, 'Nouvel appel', 'New call')}>
      <div className={styles.modal}>
        <h2 className={styles.heading}>{t(lang, 'Nouvel appel', 'New call')}</h2>

        {phase === 'form' ? (
          <form onSubmit={handleFormSubmit} noValidate>

            {/* ── Appelant ── */}
            <div className={styles.section}>
              <h3 className={styles.sectionHeading}>{t(lang, 'Appelant', 'Caller')}</h3>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label htmlFor="caller-name" className={styles.label}>{t(lang, 'Nom *', 'Name *')}</label>
                  <input id="caller-name" className={styles.input} value={callerName}
                    onChange={(e) => setCallerName(e.target.value)} data-testid="caller-name" required />
                </div>
                <div className={styles.field}>
                  <label htmlFor="phone-1" className={styles.label}>{t(lang, 'Téléphone', 'Phone')}</label>
                  <input id="phone-1" className={styles.input} value={phone1}
                    onChange={(e) => setPhone1(e.target.value)} />
                </div>
              </div>
              <div className={styles.field}>
                <label htmlFor="caller-email" className={styles.label}>{t(lang, 'Courriel', 'Email')}</label>
                <input id="caller-email" className={styles.input} type="email" value={callerEmail}
                  onChange={(e) => setCallerEmail(e.target.value)} />
              </div>
            </div>

            {/* ── Adresse ── */}
            <div className={styles.section} style={{ marginTop: 16 }}>
              <h3 className={styles.sectionHeading}>{t(lang, 'Adresse', 'Address')}</h3>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label htmlFor="civic" className={styles.label}>{t(lang, 'N° civique *', 'Civic # *')}</label>
                  <input id="civic" className={styles.input} value={civic}
                    onChange={(e) => setCivic(e.target.value)} data-testid="civic" />
                </div>
                <div className={styles.field}>
                  <label htmlFor="street" className={styles.label}>{t(lang, 'Rue *', 'Street *')}</label>
                  <input id="street" className={styles.input} value={street}
                    onChange={(e) => setStreet(e.target.value)} data-testid="street" />
                </div>
                <div className={styles.field}>
                  <label htmlFor="apartment" className={styles.label}>{t(lang, 'Appartement', 'Apartment')}</label>
                  <input id="apartment" className={styles.input} value={apartment}
                    onChange={(e) => setApartment(e.target.value)} />
                </div>
                <div className={styles.field}>
                  <label htmlFor="city" className={styles.label}>{t(lang, 'Ville', 'City')}</label>
                  <input id="city" className={styles.input} value={city}
                    onChange={(e) => setCity(e.target.value)} />
                </div>
              </div>
            </div>

            {/* ── Problème ── */}
            <div className={styles.section} style={{ marginTop: 16 }}>
              <h3 className={styles.sectionHeading}>{t(lang, 'Problème', 'Problem')}</h3>
              <div className={styles.field}>
                <label htmlFor="access" className={styles.label}>{t(lang, 'Accès au logement', 'Unit access')}</label>
                <select id="access" className={styles.select} value={access}
                  onChange={(e) => setAccess(e.target.value as typeof access)}>
                  {ACCESS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className={styles.field}>
                <label htmlFor="access-details" className={styles.label}>{t(lang, 'Précisions accès', 'Access details')}</label>
                <input id="access-details" className={styles.input} value={accessDetails}
                  onChange={(e) => setAccessDetails(e.target.value)} />
              </div>
              <div className={styles.field}>
                <label htmlFor="animals" className={styles.label}>{t(lang, 'Animaux', 'Animals')}</label>
                <select id="animals" className={styles.select} value={animals}
                  onChange={(e) => setAnimals(e.target.value as AnimalsChoice)}>
                  {ANIMALS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              {animals === 'oui' && (
                <div className={styles.field}>
                  <label htmlFor="animal-details" className={styles.label}>{t(lang, "Type d'animaux", 'Animal type')}</label>
                  <input id="animal-details" className={styles.input} value={animalDetails}
                    onChange={(e) => setAnimalDetails(e.target.value)} />
                </div>
              )}
              <div className={styles.field}>
                <label htmlFor="problem" className={styles.label}>
                  {t(lang, 'Description du problème *', 'Problem description *')}
                </label>
                <textarea id="problem" className={styles.textarea} value={problem}
                  onChange={(e) => setProblem(e.target.value)} data-testid="problem" rows={3} required />
              </div>
              <div className={`${styles.field} ${styles.attentionField}`}>
                <label htmlFor="attention" className={styles.label}>ATTENTION</label>
                <input id="attention" className={styles.input} value={attention}
                  onChange={(e) => setAttention(e.target.value)} />
              </div>
            </div>

            {errorMsg && <p className={styles.errorMsg} data-testid="error-msg">{errorMsg}</p>}

            <div className={styles.actions} style={{ marginTop: 8 }}>
              <button type="button" className={styles.cancelBtn} onClick={handleClose}>
                {t(lang, 'Annuler', 'Cancel')}
              </button>
              <button type="submit" className={styles.submitBtn} disabled={submitting} data-testid="submit-btn">
                {submitting
                  ? t(lang, 'Recherche…', 'Searching…')
                  : t(lang, "Vérifier l'adresse", 'Verify address')}
              </button>
            </div>
          </form>
        ) : (
          /* ── Confirm phase ── */
          <div>
            <button type="button" className={styles.backLink}
              onClick={() => { setPhase('form'); setErrorMsg(null); }}>
              ← {t(lang, 'Modifier', 'Edit')}
            </button>

            {matchResult && (
              <div className={styles.matchBox}>
                <p className={`${styles.matchStatus} ${MATCH_STATUS_STYLE[matchResult.match_status] ?? ''}`}>
                  {MATCH_STATUS_LABELS[matchResult.match_status] ?? matchResult.match_status}
                </p>

                {/* exact: just show building + unit */}
                {matchResult.match_status === 'exact' && (
                  <p className={styles.matchDetail}>
                    {matchResult.building_adresse ?? `Bâtiment #${matchResult.building_id}`}
                    {unitLabel ? ` — Apt ${unitLabel}` : confirmUnitId ? ` — Unité #${confirmUnitId}` : ''}
                  </p>
                )}

                {/* building_only: show building + optional unit picker */}
                {matchResult.match_status === 'building_only' && (
                  <div className={styles.section}>
                    <p className={styles.matchDetail}>
                      {matchResult.building_adresse ?? `Bâtiment #${matchResult.building_id}`}
                    </p>
                    <div className={styles.field}>
                      <label htmlFor="confirm-unit" className={styles.label}>
                        {t(lang, 'Unité (optionnel)', 'Unit (optional)')}
                      </label>
                      <select id="confirm-unit" className={styles.select} value={confirmUnitId ?? ''}
                        onChange={(e) => setConfirmUnitId(e.target.value ? Number(e.target.value) : null)}>
                        <option value="">— {t(lang, 'Aucune', 'None')} —</option>
                        {confirmUnits.map((u) => (
                          <option key={u.unit_id} value={u.unit_id}>{unitOptionLabel(u)}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}

                {/* ambiguous: pick from candidates, then optional unit */}
                {matchResult.match_status === 'ambiguous' && (
                  <div className={styles.section}>
                    <div className={styles.field}>
                      <label htmlFor="confirm-building" className={styles.label}>
                        {t(lang, 'Sélectionner le bâtiment *', 'Select building *')}
                      </label>
                      <select id="confirm-building" className={styles.select} value={confirmBuildingId ?? ''}
                        onChange={(e) => { setConfirmBuildingId(e.target.value ? Number(e.target.value) : null); setConfirmUnitId(null); }}>
                        <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                        {matchResult.candidate_buildings.map((b) => (
                          <option key={b.building_id} value={b.building_id}>
                            {b.adresse ?? `#${b.building_id}`}
                          </option>
                        ))}
                      </select>
                    </div>
                    {confirmBuildingId != null && (
                      <div className={styles.field}>
                        <label htmlFor="confirm-unit" className={styles.label}>
                          {t(lang, 'Unité (optionnel)', 'Unit (optional)')}
                        </label>
                        <select id="confirm-unit" className={styles.select} value={confirmUnitId ?? ''}
                          onChange={(e) => setConfirmUnitId(e.target.value ? Number(e.target.value) : null)}>
                          <option value="">— {t(lang, 'Aucune', 'None')} —</option>
                          {confirmUnits.map((u) => (
                            <option key={u.unit_id} value={u.unit_id}>{unitOptionLabel(u)}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                )}

                {/* no_match / garbled: full sector → building → unit picker */}
                {(matchResult.match_status === 'no_match' || matchResult.match_status === 'garbled') && (
                  <div className={styles.section}>
                    <div className={styles.field}>
                      <label htmlFor="picker-sector" className={styles.label}>
                        {t(lang, 'Secteur', 'Sector')}
                      </label>
                      <select id="picker-sector" className={styles.select} value={pickerSectorId ?? ''}
                        onChange={(e) => setPickerSectorId(e.target.value ? Number(e.target.value) : null)}>
                        <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                        {sectors.map((s) => (
                          <option key={s.sector_id} value={s.sector_id}>{s.territoire}</option>
                        ))}
                      </select>
                    </div>
                    <div className={styles.field}>
                      <label htmlFor="picker-building" className={styles.label}>
                        {t(lang, 'Bâtiment *', 'Building *')}
                      </label>
                      <select id="picker-building" className={styles.select} value={confirmBuildingId ?? ''}
                        disabled={pickerSectorId == null}
                        onChange={(e) => { setConfirmBuildingId(e.target.value ? Number(e.target.value) : null); setConfirmUnitId(null); }}
                        data-testid="building-select">
                        <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                        {pickerBuildings.map((b) => (
                          <option key={b.building_id} value={b.building_id}>
                            {b.adresse ?? b.web_building_name ?? String(b.building_id)}
                          </option>
                        ))}
                      </select>
                    </div>
                    {confirmBuildingId != null && (
                      <div className={styles.field}>
                        <label htmlFor="confirm-unit" className={styles.label}>
                          {t(lang, 'Unité (optionnel)', 'Unit (optional)')}
                        </label>
                        <select id="confirm-unit" className={styles.select} value={confirmUnitId ?? ''}
                          onChange={(e) => setConfirmUnitId(e.target.value ? Number(e.target.value) : null)}>
                          <option value="">— {t(lang, 'Aucune', 'None')} —</option>
                          {confirmUnits.map((u) => (
                            <option key={u.unit_id} value={u.unit_id}>{unitOptionLabel(u)}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {unitsError && <p className={styles.errorMsg} data-testid="units-error">{unitsError}</p>}
            {errorMsg && <p className={styles.errorMsg} data-testid="error-msg">{errorMsg}</p>}

            <div className={styles.actions} style={{ marginTop: 12 }}>
              <button type="button" className={styles.cancelBtn} onClick={handleClose}>
                {t(lang, 'Annuler', 'Cancel')}
              </button>
              <button
                type="button"
                className={styles.submitBtn}
                disabled={submitting || !confirmBuildingId}
                onClick={handleConfirm}
                data-testid="submit-btn"
              >
                {submitting
                  ? t(lang, 'Création…', 'Creating…')
                  : t(lang, 'Confirmer et créer', 'Confirm and create')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
