"use client";

import type {PaginationMeta} from "../lib/types/match";
import styles from "./Pagination.module.css";

type PaginationProps = {
  meta: PaginationMeta;
  onPageChange: (page: number) => void;
};

export default function Pagination({meta, onPageChange}: PaginationProps) {
  const {page, last_page, total} = meta;

  if (last_page <= 1) return null;

  return (
    <div className={styles.wrapper}>
      <span className={styles.total}>
        {total} match{total !== 1 ? "es" : ""} total
      </span>
      <div className={styles.controls}>
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className={styles.button}
        >
          Previous
        </button>
        <span className={styles.pageInfo}>
          Page {page} of {last_page}
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= last_page}
          className={styles.button}
        >
          Next
        </button>
      </div>
    </div>
  );
}
