import styles from "./FeatureCard.module.css";

interface FeatureCardProps {
  title: string;
  description: string;
  accents?: string[];
  variant?: "default" | "modern";
}

export default function FeatureCard({
  title,
  description,
  accents = [],
  variant = "default",
}: FeatureCardProps) {
  if (variant === "default") {
    return (
      <div className={styles.featureDefault}>
        <h3>{title}</h3>
        <p>{description}</p>
        {accents.length > 0 && (
          <div className={styles.accentContainerDefault}>
            {accents.map((accent, index) => (
              <span key={index} className={styles.accentDefault}>
                {accent}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.content}>
        <h3 className={styles.headline}>{title}</h3>
        <p className={styles.summary}>{description}</p>
      </div>
      {accents.length > 0 && (
        <div className={styles.accentContainer}>
          {accents.map((accent, index) => {
            // Calculate opacity: starts at 0.33, increases to 1
            // If only 1 item, opacity is 1
            let opacity = 1;
            if (accents.length > 1) {
              const minOpacity = 0.33;
              const step = (1 - minOpacity) / (accents.length - 1);
              opacity = minOpacity + index * step;
            }
            
            return (
              <span 
                key={index} 
                className={styles.accentText}
                style={{ opacity }}
              >
                {accent}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
