import type {Champion} from "../../lib/types/champion";
import type {
  ChampionKdaPoint,
  LaneStats,
  MatchDetail,
  MatchSummary,
  Participant,
} from "../../lib/types/match";
import type {RankInfo} from "../../lib/types/rank";
import type {UserSession} from "../../lib/types/user";

export type MatchCardProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  champion: Champion | null;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  rankByPuuid?: Record<string, RankInfo | null>;
  laneStats?: LaneStats | null;
  championHistory?: ChampionKdaPoint[];
  expanded?: boolean;
};

export type TeamsProps = {
  participants: Participant[];
  current: Participant;
  currentPuuid: string | undefined;
  version: string;
  rankByPuuid?: Record<string, RankInfo | null>;
};

export type ChampionKdaChartProps = {
  history: ChampionKdaPoint[];
  currentMatchId: string | null;
};

export type MultikillEntry = {label: string; count: number; penta: boolean};
