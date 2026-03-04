import styles from "./MatchesTable.module.css";

export default function SkeletonRows({count, colCount}: {count: number; colCount: number}) {
  return (
    <>
      {Array.from({length: count}, (_, i) => (
        <tr key={i} className={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
          {Array.from({length: colCount}, (_, j) => (
            <td key={j} className={styles.cell}>
              <div className={styles.skeletonCell} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
