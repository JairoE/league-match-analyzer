"use client";

import type {ReactNode} from "react";
import styles from "./MatchPageShell.module.css";
import Header from "../Header/Header";
import SearchBar from "../SearchBar/SearchBar";

type MatchPageShellProps = {
  subHeader: ReactNode;
  error?: string | null;
  liveGame?: ReactNode;
  children: ReactNode;
};

export default function MatchPageShell({
  subHeader,
  error,
  liveGame,
  children,
}: MatchPageShellProps) {
  return (
    <div className={styles.page}>
      <Header />
      {subHeader}
      <SearchBar />
      {liveGame}
      {error ? <p className={styles.error}>{error}</p> : null}
      {children}
    </div>
  );
}
