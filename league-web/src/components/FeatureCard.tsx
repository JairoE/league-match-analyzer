import styles from './FeatureCard.module.css';

interface FeatureCardProps {
  title: string;
  description: string;
  accentText?: string;
  variant?: 'default' | 'modern';
}

export default function FeatureCard({ 
  title, 
  description, 
  accentText,
  variant = 'default' 
}: FeatureCardProps) {
  if (variant === 'default') {
    return (
      <div className={styles.featureDefault}>
        <h3>{title}</h3>
        <p>{description}</p>
        {accentText && <span className={styles.accentDefault}>{accentText}</span>}
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.content}>
        <h3 className={styles.headline}>{title}</h3>
        <p className={styles.summary}>{description}</p>
      </div>
      {accentText && (
        <div className={styles.accentContainer}>
          <span className={styles.accentText}>{accentText}</span>
        </div>
      )}
    </div>
  );
}
