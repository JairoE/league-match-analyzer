"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./Header.module.css";
import {loadSessionUser, clearSessionUser} from "../lib/session";

type HeaderProps = {
  showBack?: boolean;
  title?: string;
  subtitle?: string;
};

export default function Header({
  showBack = false,
  title = "League Match Analyzer",
  subtitle = "Search any summoner's match history instantly",
}: HeaderProps) {
  const router = useRouter();
  const [hasSession] = useState<boolean>(() => !!loadSessionUser());

  const handleLogin = () => {
    router.push("/auth");
  };

  const handleSignOut = () => {
    clearSessionUser();
    router.push("/");
  };

  return (
    <header className={styles.header}>
      <div className={styles.content}>
        <div className={styles.text}>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>{subtitle}</p>
        </div>
        <div className={styles.actions}>
          {showBack ? (
            <button className={styles.backButton} onClick={() => router.back()}>
              &larr; Back
            </button>
          ) : hasSession ? (
            <button className={styles.signOutButton} onClick={handleSignOut}>
              Sign out
            </button>
          ) : (
            <button className={styles.loginButton} onClick={handleLogin}>
              Login
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
