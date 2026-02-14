"use client";

import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import {loadSessionUser} from "../lib/session";
import Header from "../components/Header";
import SearchBar from "../components/SearchBar";

export default function HomePage() {
  const router = useRouter();
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    const existing = loadSessionUser();
    if (existing) {
      console.debug("[home] session found, redirecting");
      router.push("/home");
    }
    setIsHydrated(true);
  }, [router]);

  if (!isHydrated) {
    return <div className={styles.loading}>Loading...</div>;
  }

  return (
    <div className={styles.page}>
      <Header />
      <main className={styles.main}>
        <SearchBar />
        <div className={styles.features}>
          <div className={styles.feature}>
            <h3>Instant Search</h3>
            <p>Search any summoner's match history without registration</p>
          </div>
          <div className={styles.feature}>
            <h3>Detailed Analytics</h3>
            <p>Deep dive into KDA, CS/min, damage share, and more</p>
          </div>
          <div className={styles.feature}>
            <h3>Champion Insights</h3>
            <p>
              Champion-specific performance metrics and build recommendations
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
