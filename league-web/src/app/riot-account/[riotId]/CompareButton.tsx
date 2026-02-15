"use client";

import {useMemo, useState} from "react";
import styles from "./page.module.css";
import {loadSessionUser} from "../../../lib/session";
import {getUserDisplayName} from "../../../lib/user-utils";

export default function CompareButton() {
  const displayName = useMemo(() => {
    const session = loadSessionUser();
    return session ? getUserDisplayName(session) : null;
  }, []);
  const [showAnalysis, setShowAnalysis] = useState(false);

  if (!displayName) return null;

  return (
    <>
      <button
        className={styles.compareButton}
        onClick={() => setShowAnalysis((prev) => !prev)}
      >
        Compare to {displayName}
      </button>
      {showAnalysis ? (
        <p className={styles.analysisBanner}>Analyzing potential match...</p>
      ) : null}
    </>
  );
}
