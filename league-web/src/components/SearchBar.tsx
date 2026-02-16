"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./SearchBar.module.css";

type SearchBarProps = {
  placeholder?: string;
  className?: string;
};

export default function SearchBar({
  placeholder = "Search summoner (e.g. Name#TAG)",
  className = "",
}: SearchBarProps) {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    router.push(`/riot-account/${encodeURIComponent(query)}`);
  };

  return (
    <form
      className={`${styles.searchForm} ${className}`}
      onSubmit={handleSearch}
    >
      <input
        className={styles.searchInput}
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder={placeholder}
      />
      <button
        className={styles.searchButton}
        type="submit"
        disabled={!searchQuery.trim()}
      >
        Search
      </button>
    </form>
  );
}
