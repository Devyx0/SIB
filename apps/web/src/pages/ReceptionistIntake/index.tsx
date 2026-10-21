import NouvelAppelModal from '../DispatchBoard/NouvelAppelModal';
import type { Lang } from '../../i18n';

/** Intake-only home for receptionist — full page, not a modal. */
export default function ReceptionistIntake({ lang }: { lang: Lang }) {
  return <NouvelAppelModal open asPage onClose={() => {}} lang={lang} />;
}
