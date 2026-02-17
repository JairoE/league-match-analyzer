"use client";

import { useState, type FormEvent } from "react";
import styles from "./AuthForm.module.css";
import { apiPost } from "../lib/api";
import { useAppError } from "../lib/errors/error-store";
import type { UserAuthPayload, UserSession } from "../lib/types/user";

type AuthFormProps = {
  title: string;
  ctaLabel: string;
  endpoint: string;
  onAuthSuccess: (user: UserSession) => void;
};

export default function AuthForm({
  title,
  ctaLabel,
  endpoint,
  onAuthSuccess,
}: AuthFormProps) {
  const [summonerName, setSummonerName] = useState("");
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const errorScope = `auth.${endpoint.replace(/[^a-zA-Z0-9]+/g, "_")}`;
  const { errorMessage, reportError, clearError } = useAppError(errorScope);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidationError(null);
    clearError();

    if (!summonerName.trim() || !email.trim()) {
      setValidationError("Summoner name and email are required.");
      return;
    }

    const payload: UserAuthPayload = {
      summoner_name: summonerName.trim(),
      email: email.trim(),
    };

    try {
      setIsSubmitting(true);
      console.debug("[auth] submit", { endpoint, payload });
      const response = await apiPost<UserAuthPayload, UserSession>(endpoint, payload);
      console.debug("[auth] success", { endpoint, response });
      clearError();
      onAuthSuccess(response);
    } catch (err) {
      console.debug("[auth] failed", { endpoint, err });
      reportError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const error = validationError ?? errorMessage;

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <h2 className={styles.title}>{title}</h2>
      <label className={styles.label}>
        Summoner name
        <input
          className={styles.input}
          type="text"
          value={summonerName}
          onChange={(event) => setSummonerName(event.target.value)}
          placeholder="Summoner name"
        />
      </label>
      <label className={styles.label}>
        Email
        <input
          className={styles.input}
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
      </label>
      {error ? <p className={styles.error}>{error}</p> : null}
      <button className={styles.button} type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Working..." : ctaLabel}
      </button>
    </form>
  );
}
