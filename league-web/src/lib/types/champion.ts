export type Champion = {
  id?: number;
  /** Riot numeric champion ID (used for spectator / participant lookups) */
  champ_id?: number;
  name?: string;
  title?: string;
  image_url?: string;
  [key: string]: unknown;
};
