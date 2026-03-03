/**
 * Data Dragon asset resolution helpers.
 *
 * Provides CDN URL builders for items, summoner spells, and rune
 * keystones. The version string should be fetched once on app load
 * from https://ddragon.leagueoflegends.com/api/versions.json and
 * cached. Falls back to FALLBACK_VERSION if unavailable.
 */

// ── Fallback version ─────────────────────────────────────────────────

export const FALLBACK_DDRAGON_VERSION = "15.4.1";

// ── Summoner Spell ID → internal name (for CDN path) ────────────────

export const SUMMONER_SPELL_MAP: Record<number, string> = {
  1: "Boost", // Cleanse
  3: "Exhaust",
  4: "Flash",
  6: "Haste", // Ghost
  7: "Heal",
  11: "Smite",
  12: "Teleport",
  13: "Mana", // Clarity (ARAM)
  14: "Dot", // Ignite
  21: "Barrier",
  30: "PoroRecall",
  31: "PoroThrow",
  32: "Snowball", // ARAM Mark/Dash
  39: "UltBook", // Ultimate Spellbook
  54: "Placeholder",
  55: "Placeholder",
};

/** User-facing spell names for alt text / tooltips */
export const SUMMONER_SPELL_LABELS: Record<number, string> = {
  1: "Cleanse",
  3: "Exhaust",
  4: "Flash",
  6: "Ghost",
  7: "Heal",
  11: "Smite",
  12: "Teleport",
  13: "Clarity",
  14: "Ignite",
  21: "Barrier",
  30: "Poro Recall",
  31: "Poro Throw",
  32: "Mark",
  39: "Placeholder",
  54: "Placeholder",
  55: "Placeholder",
};

// ── Rune style ID → path segment ────────────────────────────────────

export const RUNE_STYLE_PATHS: Record<number, string> = {
  8000: "Precision",
  8100: "Domination",
  8200: "Sorcery",
  8300: "Inspiration",
  8400: "Resolve",
};

// ── CDN URL helpers ──────────────────────────────────────────────────

export function getItemImageUrl(
  itemId: number,
  version = FALLBACK_DDRAGON_VERSION
): string {
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/item/${itemId}.png`;
}

export function getSpellImageUrl(
  spellId: number,
  version = FALLBACK_DDRAGON_VERSION
): string {
  const name = SUMMONER_SPELL_MAP[spellId] ?? "Placeholder";
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/spell/Summoner${name}.png`;
}

export function getSpellLabel(spellId: number): string {
  return SUMMONER_SPELL_LABELS[spellId] ?? "Unknown Spell";
}

/**
 * Returns CDN URL for a rune style icon (tree icon, not individual
 * keystone). Useful as a lightweight fallback.
 */
export function getRuneStyleIconUrl(styleId: number): string {
  const path = RUNE_STYLE_PATHS[styleId];
  if (!path) return "";
  return `https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/${path}/${path}.png`;
}

/**
 * Returns CDN URL for the keystone slot.
 * Individual keystone images require a perk-ID→name mapping from
 * runesReforged.json; we proxy via the rune style tree icon until
 * that mapping is loaded. The perkId is intentionally unused here
 * but kept in the signature for future specificity.
 */
export function getKeystoneImageUrl(
  _perkId: number,
  styleId: number
): string {
  return getRuneStyleIconUrl(styleId);
}

/**
 * Returns DDragon champion splash/tile icon URL.
 * `championName` must match the DDragon internal key (e.g. "Ahri",
 * "MissFortune"). Used in team composition lists.
 */
export function getChampionImageUrl(
  championName: string,
  version = FALLBACK_DDRAGON_VERSION
): string {
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${championName}.png`;
}
