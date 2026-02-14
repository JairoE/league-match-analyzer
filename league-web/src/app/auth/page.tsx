"use client";

import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import Header from "../../components/Header";
import SignInForm from "../../components/SignInForm";
import SignUpForm from "../../components/SignUpForm";
import {loadSessionUser, saveSessionUser} from "../../lib/session";
import type {UserSession} from "../../lib/types/user";

export default function AuthPage() {
  const router = useRouter();
  const [isHydrated, setIsHydrated] = useState(false);
  const [user, setUser] = useState<UserSession | null>(null);

  useEffect(() => {
    const existing = loadSessionUser();
    if (existing) {
      console.debug("[auth] session found, redirecting");
      router.push("/home");
    }
    setIsHydrated(true);
  }, [router]);

  useEffect(() => {
    if (!user) return;
    console.debug("[auth] user state set");
  }, [user]);

  const handleAuthSuccess = (user: UserSession) => {
    console.debug("[auth] storing session", {user});
    saveSessionUser(user);
    setUser(user);
    router.push("/home");
  };

  if (!isHydrated) {
    return <div className={styles.loading}>Loading session...</div>;
  }

  return (
    <div className={styles.page}>
      <Header showBack />

      <section className={styles.intro}>
        <h2>Sign In or Create Account</h2>
        <p className={styles.introSubtitle}>
          Access your saved preferences and match history
        </p>
      </section>

      <main className={styles.forms}>
        <SignInForm onAuthSuccess={handleAuthSuccess} />
        <SignUpForm onAuthSuccess={handleAuthSuccess} />
      </main>
    </div>
  );
}
