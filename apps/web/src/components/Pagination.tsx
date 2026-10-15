import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './Pagination.module.css';

interface Props {
  offset: number;
  pageSize: number;
  total: number;
  lang?: Lang;
  onPrev: () => void;
  onNext: () => void;
}

export default function Pagination({ offset, pageSize, total, lang = 'fr', onPrev, onNext }: Props) {
  if (total === 0) return null;

  const from = offset + 1;
  const to = Math.min(offset + pageSize, total);
  const hasPrev = offset > 0;
  const hasNext = offset + pageSize < total;
  const surOf = t(lang, 'sur', 'of');

  return (
    <div className={styles.wrap} data-testid="pagination">
      <span className={styles.info}>
        {from}–{to} {surOf} {total}
      </span>
      <div className={styles.buttons}>
        <button
          className={styles.btn}
          onClick={onPrev}
          disabled={!hasPrev}
          aria-label={t(lang, 'Page précédente', 'Previous page')}
          data-testid="pagination-prev"
        >
          ‹
        </button>
        <button
          className={styles.btn}
          onClick={onNext}
          disabled={!hasNext}
          aria-label={t(lang, 'Page suivante', 'Next page')}
          data-testid="pagination-next"
        >
          ›
        </button>
      </div>
    </div>
  );
}
