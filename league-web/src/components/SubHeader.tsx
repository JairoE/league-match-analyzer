import type {ReactNode} from "react";
import styles from "./SubHeader.module.css";

type SubHeaderProps = {
  kicker: string;
  title: string;
  subtitle?: string | null;
  actions?: ReactNode;
};

export default function SubHeader({
  kicker,
  title,
  subtitle,
  actions,
}: SubHeaderProps) {
  return (
    <section className={styles.subHeader}>
      <div>
        <p className={styles.kicker}>{kicker}</p>
        <h2 className={styles.title}>{title}</h2>
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </section>
  );
}
