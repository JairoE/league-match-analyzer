import type {Participant} from "../../lib/types/match";
import type {MultikillEntry} from "./types";

export function diffLabel(val: number | null | undefined): string | null {
  if (val == null) return null;
  return val > 0 ? `+${val}` : String(val);
}

export function getMultikillBadges(participant: Participant | null): MultikillEntry[] {
  const rawDoubles = participant?.doubleKills ?? 0;
  const rawTriples = participant?.tripleKills ?? 0;
  const rawQuadras = participant?.quadraKills ?? 0;
  const rawPentas = participant?.pentaKills ?? 0;
  return (
    [
      {label: "Double Kill", count: rawDoubles - rawTriples, penta: false},
      {label: "Triple Kill", count: rawTriples - rawQuadras, penta: false},
      {label: "Quadra Kill", count: rawQuadras - rawPentas, penta: false},
      {label: "Penta Kill", count: rawPentas, penta: true},
    ] as MultikillEntry[]
  ).filter((mk) => mk.count > 0);
}

type OutcomeDisplay = {
  outcomeClass: string;
  textQueueClass: string;
  outcomeLabel: string;
};

export function getOutcomeDisplay(
  outcome: string,
  styles: Record<string, string>
): OutcomeDisplay {
  const outcomeClass =
    outcome === "victory"
      ? styles.cardVictory
      : outcome === "defeat"
        ? styles.cardDefeat
        : styles.cardRemake;

  const textQueueClass =
    outcome === "victory"
      ? styles.textBlue
      : outcome === "defeat"
        ? styles.textRed
        : styles.textGray;

  const outcomeLabel =
    outcome === "victory" ? "Victory" : outcome === "defeat" ? "Defeat" : "Remake";

  return {outcomeClass, textQueueClass, outcomeLabel};
}
