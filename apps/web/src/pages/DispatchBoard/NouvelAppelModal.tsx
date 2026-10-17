import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  createManualRequest, fetchBuildings, fetchSectors, fetchUnits,
} from '../../api/client';
import type { BuildingLookup, SectorLookup, UnitLookup } from '../../api/client';
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

export default function NouvelAppelModal({ open, onClose, lang = 'fr' }: Props) {
  const qc = useQueryClient();

  // Caller fields
  const [callerName, setCallerName] = useState('');
  const [phone1, setPhone1] = useState('');
  const [callerEmail, setCallerEmail] = useState('');

  // Address fields
  const [civic, setCivic] = useState('');
  const [street, setStreet] = useState('');
  const [apartment, setApartment] = useState('');
  const [city, setCity] = useState('Québec');

  // Problem fields
  const [access, setAccess] = useState<'yes' | 'tenant_required' | 'common_area' | 'unknown'>('yes');
  const [accessDetails, setAccessDetails] = useState('');
  const [hasAnimals, setHasAnimals] = useState(false);
  const [animalDetails, setAnimalDetails] = useState('');
  const [problem, setProblem] = useState('');
  const [attention, setAttention] = useState('');

  // Building picker
  const [showPicker, setShowPicker] = useState(false);
  const [sectors, setSectors] = useState<SectorLookup[]>([]);
  const [buildings, setBuildings] = useState<BuildingLookup[]>([]);
  const [units, setUnits] = useState<UnitLookup[]>([]);
  const [pickerSectorId, setPickerSectorId] = useState<number | null>(null);
  const [pickerBuildingId, setPickerBuildingId] = useState<number | null>(null);
  const [pickerUnitId, setPickerUnitId] = useState<number | null>(null);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open && showPicker && sectors.length === 0) {
      fetchSectors().then(setSectors).catch(() => {});
    }
  }, [open, showPicker, sectors.length]);

  useEffect(() => {
    if (pickerSectorId != null) {
      fetchBuildings(pickerSectorId).then(setBuildings).catch(() => {});
      setPickerBuildingId(null);
      setPickerUnitId(null);
      setUnits([]);
    }
  }, [pickerSectorId]);

  useEffect(() => {
    if (pickerBuildingId != null) {
      fetchUnits(pickerBuildingId).then(setUnits).catch(() => {});
      setPickerUnitId(null);
    }
  }, [pickerBuildingId]);

  function reset() {
    setCallerName(''); setPhone1(''); setCallerEmail('');
    setCivic(''); setStreet(''); setApartment(''); setCity('Québec');
    setAccess('yes'); setAccessDetails(''); setHasAnimals(false);
    setAnimalDetails(''); setProblem(''); setAttention('');
    setShowPicker(false); setSectors([]); setBuildings([]); setUnits([]);
    setPickerSectorId(null); setPickerBuildingId(null); setPickerUnitId(null);
    setSubmitting(false); setErrorMsg(null); setSuccessMsg(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!callerName.trim()) { setErrorMsg(t(lang, 'Nom requis.', 'Name required.')); return; }
    if (!problem.trim()) { setErrorMsg(t(lang, 'Problème requis.', 'Problem required.')); return; }

    let civicVal = civic.trim();
    let streetVal = street.trim();

    if (showPicker && pickerBuildingId != null) {
      // Use picker override — extract civic/street from building adresse for schema compliance
      const bldg = buildings.find((b) => b.building_id === pickerBuildingId);
      const adresse = bldg?.adresse ?? '';
      const firstSlash = adresse.indexOf(' / ');
      const seg = firstSlash >= 0 ? adresse.slice(0, firstSlash) : adresse;
      const match = seg.match(/^(\d[\d\-]*)?\s*(.+)$/);
      civicVal = match?.[1] ?? '0';
      streetVal = match?.[2]?.trim() || adresse || 'immeuble';
    } else if (!civicVal || !streetVal) {
      setErrorMsg(t(lang, 'Numéro civique et rue requis.', 'Civic number and street required.'));
      return;
    }

    setSubmitting(true);
    try {
      const body = {
        caller_name: callerName.trim(),
        phone_1: phone1.trim() || undefined,
        caller_email: callerEmail.trim() || undefined,
        civic: civicVal,
        street: streetVal,
        apartment: apartment.trim() || undefined,
        city: city.trim() || 'Québec',
        access,
        access_details: accessDetails.trim() || undefined,
        has_animals: hasAnimals,
        animal_details: hasAnimals ? (animalDetails.trim() || undefined) : undefined,
        problem: problem.trim(),
        attention: attention.trim() || undefined,
        ...(showPicker && pickerBuildingId != null
          ? { building_id_override: pickerBuildingId, unit_id_override: pickerUnitId ?? undefined }
          : {}),
      };

      const result = await createManualRequest(body);
      qc.invalidateQueries({ queryKey: ['requests'] });

      if (result.match_status === 'no_match' || result.match_status === 'ambiguous' || result.match_status === 'garbled') {
        setSuccessMsg(
          t(lang,
            `Demande #${result.request_id} créée sans bâtiment (adresse introuvable). Sélectionnez depuis la liste.`,
            `Request #${result.request_id} created without building (address not found). Use the list picker.`,
          )
        );
        setShowPicker(true);
        if (sectors.length === 0) fetchSectors().then(setSectors).catch(() => {});
      } else {
        handleClose();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className={styles.overlay} role="dialog" aria-modal aria-label={t(lang, 'Nouvel appel', 'New call')}>
      <div className={styles.modal}>
        <h2 className={styles.heading}>{t(lang, 'Nouvel appel', 'New call')}</h2>

        <form onSubmit={handleSubmit} noValidate>
          {/* Appelant */}
          <div className={styles.section}>
            <h3 className={styles.sectionHeading}>{t(lang, 'Appelant', 'Caller')}</h3>
            <div className={styles.row}>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Nom *', 'Name *')}</label>
                <input className={styles.input} value={callerName} onChange={(e) => setCallerName(e.target.value)}
                  data-testid="caller-name" required />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Téléphone', 'Phone')}</label>
                <input className={styles.input} value={phone1} onChange={(e) => setPhone1(e.target.value)} />
              </div>
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Courriel', 'Email')}</label>
              <input className={styles.input} type="email" value={callerEmail}
                onChange={(e) => setCallerEmail(e.target.value)} />
            </div>
          </div>

          {/* Adresse */}
          <div className={styles.section} style={{ marginTop: 16 }}>
            <h3 className={styles.sectionHeading}>{t(lang, 'Adresse', 'Address')}</h3>
            <div className={styles.row}>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'N° civique', 'Civic #')}</label>
                <input className={styles.input} value={civic} onChange={(e) => setCivic(e.target.value)}
                  data-testid="civic" />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Rue', 'Street')}</label>
                <input className={styles.input} value={street} onChange={(e) => setStreet(e.target.value)}
                  data-testid="street" />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Appartement', 'Apartment')}</label>
                <input className={styles.input} value={apartment} onChange={(e) => setApartment(e.target.value)} />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Ville', 'City')}</label>
                <input className={styles.input} value={city} onChange={(e) => setCity(e.target.value)} />
              </div>
            </div>

            <button type="button" className={styles.pickerToggle} onClick={() => setShowPicker((b) => !b)}>
              {showPicker
                ? t(lang, '▲ Masquer la liste de bâtiments', '▲ Hide building list')
                : t(lang, '▼ Ou sélectionner depuis la liste', '▼ Or choose from list')}
            </button>

            {showPicker && (
              <div className={styles.pickerSection} data-testid="building-picker">
                <div className={styles.field}>
                  <label className={styles.label}>{t(lang, 'Secteur', 'Sector')}</label>
                  <select className={styles.select} value={pickerSectorId ?? ''}
                    onChange={(e) => setPickerSectorId(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                    {sectors.map((s) => (
                      <option key={s.sector_id} value={s.sector_id}>{s.territoire}</option>
                    ))}
                  </select>
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>{t(lang, 'Bâtiment', 'Building')}</label>
                  <select className={styles.select} value={pickerBuildingId ?? ''}
                    disabled={pickerSectorId == null}
                    onChange={(e) => setPickerBuildingId(e.target.value ? Number(e.target.value) : null)}
                    data-testid="building-select">
                    <option value="">— {t(lang, 'Choisir', 'Choose')} —</option>
                    {buildings.map((b) => (
                      <option key={b.building_id} value={b.building_id}>
                        {b.adresse ?? b.web_building_name ?? String(b.building_id)}
                      </option>
                    ))}
                  </select>
                </div>
                {units.length > 0 && (
                  <div className={styles.field}>
                    <label className={styles.label}>{t(lang, 'Unité (optionnel)', 'Unit (optional)')}</label>
                    <select className={styles.select} value={pickerUnitId ?? ''}
                      onChange={(e) => setPickerUnitId(e.target.value ? Number(e.target.value) : null)}>
                      <option value="">— {t(lang, 'Aucune', 'None')} —</option>
                      {units.map((u) => (
                        <option key={u.unit_id} value={u.unit_id}>{u.numero_appartement}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Problème */}
          <div className={styles.section} style={{ marginTop: 16 }}>
            <h3 className={styles.sectionHeading}>{t(lang, 'Problème', 'Problem')}</h3>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Accès au logement', 'Unit access')}</label>
              <select className={styles.select} value={access}
                onChange={(e) => setAccess(e.target.value as typeof access)}>
                {ACCESS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Précisions accès', 'Access details')}</label>
              <input className={styles.input} value={accessDetails}
                onChange={(e) => setAccessDetails(e.target.value)} />
            </div>
            <div className={styles.checkRow}>
              <input id="has-animals" type="checkbox" checked={hasAnimals}
                onChange={(e) => setHasAnimals(e.target.checked)} />
              <label htmlFor="has-animals">{t(lang, 'Animaux dans le logement', 'Animals present')}</label>
            </div>
            {hasAnimals && (
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, 'Type d\'animaux', 'Animal type')}</label>
                <input className={styles.input} value={animalDetails}
                  onChange={(e) => setAnimalDetails(e.target.value)} />
              </div>
            )}
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Description du problème *', 'Problem description *')}</label>
              <textarea className={styles.textarea} value={problem}
                onChange={(e) => setProblem(e.target.value)}
                data-testid="problem" rows={3} required />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'ATTENTION', 'ATTENTION')}</label>
              <input className={styles.input} value={attention}
                onChange={(e) => setAttention(e.target.value)} />
            </div>
          </div>

          {errorMsg && <p className={styles.errorMsg} data-testid="error-msg">{errorMsg}</p>}
          {successMsg && <p className={styles.successMsg} data-testid="success-msg">{successMsg}</p>}

          <div className={styles.actions} style={{ marginTop: 8 }}>
            <button type="button" className={styles.cancelBtn} onClick={handleClose}>
              {t(lang, 'Annuler', 'Cancel')}
            </button>
            <button type="submit" className={styles.submitBtn} disabled={submitting}
              data-testid="submit-btn">
              {submitting
                ? t(lang, 'Création…', 'Creating…')
                : t(lang, 'Créer l\'appel', 'Create call')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
