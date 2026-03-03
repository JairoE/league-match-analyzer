/** High-level bucket for UX & filters */
export enum GameQueueGroup {
  RANKED_SOLO = "RANKED_SOLO",
  RANKED_FLEX = "RANKED_FLEX",
  NORMAL_SR = "NORMAL_SR",
  ARAM = "ARAM",
  ARENA = "ARENA",
  SWIFTPLAY = "SWIFTPLAY",
  EVENT = "EVENT",
  OTHER = "OTHER",
}

/** Granular game mode label for UI chips / routing */
export enum GameQueueMode {
  RANKED_SOLO = "RANKED_SOLO",
  RANKED_FLEX = "RANKED_FLEX",
  NORMAL_DRAFT = "NORMAL_DRAFT",
  NORMAL_BLIND = "NORMAL_BLIND",
  SWIFTPLAY = "SWIFTPLAY",
  ARAM = "ARAM",
  ARAM_MAYHEM = "ARAM_MAYHEM",
  ARENA = "ARENA",
  URF = "URF",
  NEXUS_BLITZ = "NEXUS_BLITZ",
  PRACTICE_TOOL = "PRACTICE_TOOL",
  OTHER = "OTHER",
}

/** Concrete Riot queue IDs */
export enum RiotQueueId {
  RANKED_SOLO_5V5 = 420,
  RANKED_FLEX_5V5 = 440,
  NORMAL_DRAFT_5V5 = 400,
  NORMAL_BLIND_5V5 = 430,
  ARAM = 450,
  SWIFTPLAY = 480,
  ARAM_MAYHEM = 0,
}

const QUEUE_ID_TO_GROUP: Record<number, GameQueueGroup> = {
  [RiotQueueId.RANKED_SOLO_5V5]: GameQueueGroup.RANKED_SOLO,
  [RiotQueueId.RANKED_FLEX_5V5]: GameQueueGroup.RANKED_FLEX,
  [RiotQueueId.NORMAL_DRAFT_5V5]: GameQueueGroup.NORMAL_SR,
  [RiotQueueId.NORMAL_BLIND_5V5]: GameQueueGroup.NORMAL_SR,
  [RiotQueueId.ARAM]: GameQueueGroup.ARAM,
  [RiotQueueId.SWIFTPLAY]: GameQueueGroup.SWIFTPLAY,
};

const QUEUE_ID_TO_MODE: Record<number, GameQueueMode> = {
  [RiotQueueId.RANKED_SOLO_5V5]: GameQueueMode.RANKED_SOLO,
  [RiotQueueId.RANKED_FLEX_5V5]: GameQueueMode.RANKED_FLEX,
  [RiotQueueId.NORMAL_DRAFT_5V5]: GameQueueMode.NORMAL_DRAFT,
  [RiotQueueId.NORMAL_BLIND_5V5]: GameQueueMode.NORMAL_BLIND,
  [RiotQueueId.ARAM]: GameQueueMode.ARAM,
  [RiotQueueId.SWIFTPLAY]: GameQueueMode.SWIFTPLAY,
};

/** Map a Riot queueId to a high-level group for tab filtering */
export function getQueueGroup(queueId: number | undefined | null): GameQueueGroup {
  if (queueId == null) return GameQueueGroup.OTHER;
  return QUEUE_ID_TO_GROUP[queueId] ?? GameQueueGroup.OTHER;
}

/** Map a Riot queueId to a granular mode for display */
export function getQueueMode(queueId: number | undefined | null): GameQueueMode {
  if (queueId == null) return GameQueueMode.OTHER;
  return QUEUE_ID_TO_MODE[queueId] ?? GameQueueMode.OTHER;
}

/** User-facing label for a queue group */
const GROUP_LABELS: Record<GameQueueGroup, string> = {
  [GameQueueGroup.RANKED_SOLO]: "Ranked Solo",
  [GameQueueGroup.RANKED_FLEX]: "Ranked Flex",
  [GameQueueGroup.NORMAL_SR]: "Normal",
  [GameQueueGroup.ARAM]: "ARAM",
  [GameQueueGroup.ARENA]: "Arena",
  [GameQueueGroup.SWIFTPLAY]: "Swiftplay",
  [GameQueueGroup.EVENT]: "Event",
  [GameQueueGroup.OTHER]: "Other",
};

/** User-facing label for a queue mode */
const MODE_LABELS: Record<GameQueueMode, string> = {
  [GameQueueMode.RANKED_SOLO]: "Ranked Solo",
  [GameQueueMode.RANKED_FLEX]: "Ranked Flex",
  [GameQueueMode.NORMAL_DRAFT]: "Normal Draft",
  [GameQueueMode.NORMAL_BLIND]: "Normal Blind",
  [GameQueueMode.SWIFTPLAY]: "Swiftplay",
  [GameQueueMode.ARAM]: "ARAM",
  [GameQueueMode.ARAM_MAYHEM]: "ARAM Mayhem",
  [GameQueueMode.ARENA]: "Arena",
  [GameQueueMode.URF]: "URF",
  [GameQueueMode.NEXUS_BLITZ]: "Nexus Blitz",
  [GameQueueMode.PRACTICE_TOOL]: "Practice Tool",
  [GameQueueMode.OTHER]: "Other",
};

export function getQueueGroupLabel(group: GameQueueGroup): string {
  return GROUP_LABELS[group];
}

export function getQueueModeLabel(mode: GameQueueMode): string {
  return MODE_LABELS[mode];
}
