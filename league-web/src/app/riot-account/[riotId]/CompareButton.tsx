"use client";

import {useEffect, useState} from "react";
import styles from "./page.module.css";
import {loadSessionUser} from "../../../lib/session";
import {getUserDisplayName} from "../../../lib/user-utils";

export default function CompareButton() {
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [showAnalysis, setShowAnalysis] = useState(false);

  useEffect(() => {
    const session = loadSessionUser();
    if (session) {
      setDisplayName(getUserDisplayName(session));
    }
  }, []);

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
