"use client";

import {useEffect, useState, Suspense} from "react";
import {useRouter, useSearchParams} from "next/navigation";
import styles from "./page.module.css";
import {loadSessionUser} from "../lib/session";
import Header from "../components/Header";
import SearchBar from "../components/SearchBar";
import FeatureCard from "../components/FeatureCard";

const FEATURES = [
  {
    title: "Instant Search",
    description: "Search any summoner's match history without registration",
    accents: ["Fast"],
  },
  {
    title: "Detailed Analytics",
    description: "Deep dive into KDA, CS/min, damage share, and more",
    accents: ["Deep Dive", "Stats", "Charts"],
  },
  {
    title: "Summoner to Summoner Compatibility",
    description:
      "Compare your summoner's match history with another summoner's match history",
    accents: ["New", "Compare"],
  },
  {
    title: "Live Game Stats",
    description:
      "Run locally while playing a game to get live stats (gold, CS, items, spells, runes, etc.)",
    accents: ["Real-time", "Local"],
  },
  {
    title: "LLM-Powered Analysis (AI coaching copilot)",
    description:
      "Analyze match data and get personalized champion pool recommendations, build suggestions, and game coaching.",
    accents: [
      "Time for a new lane?",
      "Time to let go of your favorite champion?",
      "Let the AI help you decide.",
    ],
  },
];

function LandingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [hasSession] = useState<boolean>(() => !!loadSessionUser());
  const design = searchParams.get("design");

  useEffect(() => {
    if (hasSession) {
      console.debug("[landing] session found, redirecting");
      router.push("/home");
    }
  }, [hasSession, router]);

  if (hasSession) {
    return <div className={styles.loading}>Redirecting...</div>;
  }

  return (
    <div className={styles.page}>
      <Header />
      <main className={styles.main}>
        <SearchBar />
        <div className={styles.features}>
          {FEATURES.map((feature, i) => (
            <FeatureCard
              key={i}
              title={feature.title}
              description={feature.description}
              accents={feature.accents}
              variant={design === "modern" ? "modern" : "default"}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

export default function LandingPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LandingContent />
    </Suspense>
  );
}
