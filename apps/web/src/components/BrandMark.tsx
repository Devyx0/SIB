import styles from './BrandMark.module.css';

interface Props {
  /** Product line under the wordmark, e.g. "Maintenance". */
  product?: string;
  size?: 'sm' | 'md';
}

// Block monogram from the Société immobilière Bélanger logo: a charcoal
// pillar, a stone-grey square over a navy square.
export default function BrandMark({ product, size = 'md' }: Props) {
  return (
    <span className={`${styles.brand} ${size === 'sm' ? styles.sm : ''}`}>
      <svg className={styles.mark} viewBox="0 0 40 40" aria-hidden="true">
        <rect x="0" y="0" width="18" height="40" fill="var(--charcoal)" />
        <rect x="21" y="0" width="19" height="18.5" fill="var(--stone)" />
        <rect x="21" y="21.5" width="19" height="18.5" fill="var(--navy-800)" />
      </svg>
      <span className={styles.words}>
        <span className={styles.company}>Société immobilière</span>
        <span className={styles.name}>Bélanger</span>
        {product && <span className={styles.product}>{product}</span>}
      </span>
    </span>
  );
}
