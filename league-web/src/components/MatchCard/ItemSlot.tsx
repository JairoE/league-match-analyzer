/*
 * eslint-disable @next/next/no-img-element
 *
 * Uses <img> (not <Image>) for external DDragon CDN assets with onError fallback.
 */
/* eslint-disable @next/next/no-img-element */

import styles from "./MatchCard.module.css";
import {getItemImageUrl} from "../../lib/constants/ddragon";

export function ItemSlot({itemId, version}: {itemId: number; version: string}) {
  if (itemId === 0) {
    return <div className={styles.itemSlotEmpty} aria-hidden="true" />;
  }
  return (
    <img
      src={getItemImageUrl(itemId, version)}
      alt={`Item ${itemId}`}
      className={styles.itemSlot}
      width={22}
      height={22}
      loading="lazy"
      onError={(e) => {
        (e.target as HTMLImageElement).style.display = "none";
      }}
    />
  );
}
