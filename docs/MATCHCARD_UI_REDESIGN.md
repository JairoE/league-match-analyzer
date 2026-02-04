# MatchCard UI Redesign - Analysis & Implementation Plan

## Executive Summary

**Good news**: 90% of the data needed is already being fetched from Riot API and stored in our database.

**The problem**: Our frontend TypeScript types don't expose these fields, making them inaccessible in components.

**The solution**: This is primarily a **frontend refactor** - update types, restructure components, and apply new styling. Minimal backend work needed.

**Complexity**: Medium. Involves component restructuring, type updates, and CSS redesign. No new API integrations required for core features.

---

## Screenshot Analysis

The target UI shows three distinct match card states with significantly more data than our current implementation.

### Match States (Enum Required)

```typescript
enum MatchOutcome {
  DEFEAT = "defeat",
  REMAKE = "remake",
  VICTORY = "victory",
}
```

**Visual Treatment:**

- **DEFEAT**: Red/dark red background (#4a2828 or similar)
- **REMAKE**: Gray/neutral background (#3a3a3a or similar)
- **VICTORY**: Blue background (#2c4a6e or similar)

---

## UI Elements Breakdown (Left to Right)

### Left Column (Primary Info)

1. **Queue Type** (top-left)

   - Text: "Ranked Solo/Duo"
   - Current: ❌ Not displayed
   - Data: ✅ Available via `detail.info.queueId` (needs mapping)

2. **Time Ago** (below queue)

   - Text: "1 day ago", "2 days ago", "3 days ago"
   - Current: ❌ Not displayed
   - Data: ✅ Available via `match.gameCreation` or `match.gameStartTimestamp`

3. **Match Outcome Label**

   - Text: "Defeat", "Remake", "Victory"
   - Current: ✅ Partial (shows "Win"/"Loss" inline with champion name)
   - Data: ✅ Available via `participant.win` + `participant.gameEndedInEarlySurrender`

4. **Match Duration**
   - Text: "35m 44s", "1m 29s", "20m 25s"
   - Current: ✅ Available but in seconds only ("Game duration: X sec")
   - Data: ✅ Available via `detail.info.gameDuration`

### Center Section (Champion & Stats)

5. **Champion Portrait**

   - Large circular avatar with border
   - Current: ✅ Has image but small square format
   - Data: ✅ Available via `champion.imageUrl`

6. **Champion Level Badge**

   - Small circular badge on champion portrait (e.g., "15", "10")
   - Current: ❌ Not displayed
   - Data: ⚠️ **MISSING** - Need `participant.champLevel`

7. **Primary Stats (K/D/A Display)**

   - Format: "8 / 9 / 7"
   - Large, bold numbers with color coding (kills green, deaths red)
   - Current: ✅ Data available but shown in dropdown only
   - Data: ✅ Available via `participant.kills`, `participant.deaths`, `participant.assists`

8. **KDA Ratio**

   - Format: "1.67:1 KDA"
   - Current: ✅ Calculated and displayed
   - Data: ✅ Computed

9. **Item Build (6 items + trinket)**

   - 6 main item slots + 1 trinket slot
   - Visual: Small square icons with item images
   - Current: ❌ Not displayed
   - Data: ⚠️ **MISSING** - Need `participant.item0` through `participant.item6`

10. **Summoner Spells** (2 icons)

    - Visual: Two spell icons near champion portrait
    - Current: ❌ Not displayed
    - Data: ⚠️ **MISSING** - Need `participant.summoner1Id`, `participant.summoner2Id`

11. **Runes/Keystone** (2 small icons)

    - Visual: Keystone + secondary rune tree icon
    - Current: ❌ Not displayed
    - Data: ⚠️ **MISSING** - Need `participant.perks` data

12. **Achievement Badges**
    - Examples: "Double Kill", "7th", "Downfall", "3rd", "Victor"
    - Visual: Rounded pill badges with distinct colors
    - Current: ❌ Not displayed
    - Data: ⚠️ **PARTIALLY MISSING** - May need custom logic or API data

### Right Column (Team Composition & Stats)

13. **Player List (All 10 Players)**

    - Left side: Allied team (5 players)
    - Right side: Enemy team (5 players)
    - Format: Champion icon + summoner name
    - Current player highlighted (bold text: "damanjr")
    - Current: ❌ Not displayed
    - Data: ✅ Available via `detail.info.participants[]`

14. **Advanced Stats (Top-right corner)**

    - **Laning Phase Score**: "Laning 43 : 57"
    - **Kill Participation**: "P/Kill 60%"
    - **CS Score**: "CS 103 (5)"
    - **Current Rank**: "Silver 2", "Silver 4", "Bronze 1"
    - Current: ❌ Not displayed
    - Data: ⚠️ **MOSTLY MISSING**:
      - CS available: ✅ `participant.totalMinionsKilled + participant.neutralMinionsKilled`
      - Kill participation: ✅ Computable from kills/assists vs team totals
      - Laning score: ❌ **MISSING** (requires timeline data)
      - Rank: ❌ **MISSING** (requires separate rank API call)

15. **Expand/Collapse Button**
    - Visual: Chevron icon on far right
    - Current: ✅ Has toggle button
    - Data: N/A (UI state only)

---

## Data Availability Matrix

| UI Element          | Current Display | Data Available | Data Source                   | Action Required                |
| ------------------- | --------------- | -------------- | ----------------------------- | ------------------------------ |
| Queue Type          | ❌              | ✅             | `queueId`                     | Map queue ID to name           |
| Time Ago            | ❌              | ✅             | `gameCreation`                | Format relative time           |
| Outcome State       | Partial         | ✅             | `participant.win`             | Create enum, apply styles      |
| Duration            | ✅ (seconds)    | ✅             | `gameDuration`                | Format to "Xm Ys"              |
| Champion Portrait   | ✅ (small)      | ✅             | `champion.imageUrl`           | Resize, apply circular styling |
| Champion Level      | ❌              | ❌             | `participant.champLevel`      | **Add to Participant type**    |
| K/D/A Large Display | Hidden          | ✅             | `kills/deaths/assists`        | Move to card front             |
| KDA Ratio           | ✅              | ✅             | Computed                      | Keep existing                  |
| Items (7 slots)     | ❌              | ❌             | `participant.item0-6`         | **Add to Participant type**    |
| Summoner Spells     | ❌              | ❌             | `participant.summoner1Id/2Id` | **Add to Participant type**    |
| Runes               | ❌              | ❌             | `participant.perks`           | **Add to Participant type**    |
| Achievement Badges  | ❌              | ⚠️             | Various                       | **Requires logic + data**      |
| All Players List    | ❌              | ✅             | `participants[]`              | Build team lists               |
| Laning Score        | ❌              | ❌             | Timeline API                  | **Needs separate endpoint**    |
| Kill Participation  | ❌              | ✅             | Computed                      | Calculate (K+A)/teamKills      |
| CS Score            | ❌              | ✅             | `totalMinionsKilled`          | Display value                  |
| Rank Badge          | ❌              | ❌             | Rank API                      | **Needs separate endpoint**    |

---

## Implementation Strategy

### Phase 1: Type System Updates

**File: `src/lib/types/match.ts`**

```typescript
// Add to Participant type
export type Participant = {
  // ... existing fields
  champLevel?: number;
  item0?: number;
  item1?: number;
  item2?: number;
  item3?: number;
  item4?: number;
  item5?: number;
  item6?: number; // trinket
  summoner1Id?: number;
  summoner2Id?: number;
  perks?: ParticipantPerks;
  gameEndedInEarlySurrender?: boolean;
  teamEarlySurrendered?: boolean;
  // ... rest
};

export type ParticipantPerks = {
  statPerks?: {
    defense?: number;
    flex?: number;
    offense?: number;
  };
  styles?: PerkStyle[];
};

export type PerkStyle = {
  description?: string;
  selections?: PerkSelection[];
  style?: number;
};

export type PerkSelection = {
  perk?: number;
  var1?: number;
  var2?: number;
  var3?: number;
};

// New enum for match outcome
export enum MatchOutcome {
  DEFEAT = "defeat",
  REMAKE = "remake",
  VICTORY = "victory",
}

// Queue ID mapping
export const QUEUE_ID_MAP: Record<number, string> = {
  420: "Ranked Solo/Duo",
  440: "Ranked Flex",
  450: "ARAM",
  400: "Normal Draft",
  430: "Normal Blind",
  // Add more as needed
};
```

### Phase 2: Utility Functions

**File: `src/lib/match-utils.ts`**

```typescript
export function getMatchOutcome(
  participant: Participant | null
): MatchOutcome | null {
  if (!participant) return null;

  // Check for remake first (usually gameEndedInEarlySurrender + very short duration)
  if (
    participant.gameEndedInEarlySurrender ||
    participant.teamEarlySurrendered
  ) {
    return MatchOutcome.REMAKE;
  }

  return participant.win ? MatchOutcome.VICTORY : MatchOutcome.DEFEAT;
}

export function formatGameDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

export function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diffMs = now - timestamp;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

export function getQueueName(queueId: number | undefined): string {
  if (!queueId) return "Unknown Queue";
  return QUEUE_ID_MAP[queueId] ?? `Queue ${queueId}`;
}

export function calculateKillParticipation(
  participant: Participant | null,
  allParticipants: Participant[]
): number {
  if (!participant) return 0;

  const teamParticipants = allParticipants.filter(
    (p) => p.teamId === participant.teamId
  );
  const teamKills = teamParticipants.reduce(
    (sum, p) => sum + (p.kills ?? 0),
    0
  );

  if (teamKills === 0) return 0;

  const playerContribution =
    (participant.kills ?? 0) + (participant.assists ?? 0);
  return (playerContribution / teamKills) * 100;
}

export function getAlliedTeam(
  participants: Participant[],
  currentParticipant: Participant
): Participant[] {
  return participants.filter((p) => p.teamId === currentParticipant.teamId);
}

export function getEnemyTeam(
  participants: Participant[],
  currentParticipant: Participant
): Participant[] {
  return participants.filter((p) => p.teamId !== currentParticipant.teamId);
}
```

### Phase 3: Component Structure

**New file structure:**

```
src/
  components/
    MatchCard/
      MatchCard.tsx              // Main container
      MatchCard.module.css       // Styles
      MatchCardHeader.tsx        // Queue + time
      MatchCardChampion.tsx      // Champion portrait + level
      MatchCardStats.tsx         // K/D/A + KDA ratio
      MatchCardItems.tsx         // Item build
      MatchCardSpells.tsx        // Summoner spells + runes
      MatchCardBadges.tsx        // Achievement badges
      MatchCardTeams.tsx         // Player lists
      MatchCardAdvanced.tsx      // Laning, P/Kill, CS, Rank
```

### Phase 4: Placeholder Strategy

For missing data, use this pattern:

```typescript
// For images (items, summoner spells, runes)
const itemUrl = itemId
  ? `https://ddragon.leagueoflegends.com/cdn/14.1.1/img/item/${itemId}.png`
  : "/placeholder-item.png"; // Gray square with "?"

// For text data
const champLevel = participant?.champLevel ?? "missing";
const laningScore = "missing"; // Until timeline API integrated
const rank = "missing"; // Until rank API integrated

// For achievement badges
// Skip rendering if data unavailable (don't show "missing")
```

### Phase 5: Styling Requirements

**Color Palette:**

```css
/* Match outcome backgrounds */
--match-defeat: #4a2828;
--match-remake: #3a3a3a;
--match-victory: #2c4a6e;

/* Stat colors */
--stat-kills: #4ade80;
--stat-deaths: #f87171;
--stat-assists: #60a5fa;

/* Badge colors */
--badge-doublekill: #ef4444;
--badge-rank: #a78bfa;
--badge-performance: #fbbf24;
```

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Queue Type                            Players List    | Expand  │
│ Time Ago                              [Team 1]        | Button  │
│                                       [Team 2]        |         │
│ OUTCOME LABEL    [Champion]  K/D/A   ───────────────  |         │
│ Duration         [Level  ]   Ratio   Advanced Stats   |         │
│                  [Spells ]   Items   - Laning         |         │
│                  [Runes  ]   [6+1]   - P/Kill         |         │
│                  Badges              - CS             |         │
│                                      - Rank           |         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Missing Data - Backend Requirements

### ✅ GOOD NEWS: Most data is already available!

The Riot Match API (`fetch_match_by_id`) returns the complete match payload, which includes:

- ✅ Champion level (`champLevel`)
- ✅ Items (`item0` through `item6`)
- ✅ Summoner spells (`summoner1Id`, `summoner2Id`)
- ✅ Runes/Perks (`perks` object)
- ✅ Remake flags (`gameEndedInEarlySurrender`, `teamEarlySurrendered`)
- ✅ Kill counts (`doubleKills`, `tripleKills`, `quadraKills`, `pentaKills`)
- ✅ All participant data for team composition display

**This data is stored in `Match.game_info` JSONB and returned to the frontend.**

### The ONLY issue: TypeScript types are incomplete

Our `Participant` type in `src/lib/types/match.ts` doesn't define these fields, so they're inaccessible in the component code.

### Still Missing (requires new API calls):

1. **Laning Stats**: Requires Timeline API endpoint (`/lol/match/v5/matches/{matchId}/timeline`)

   - CS difference at 10/15 minutes
   - Gold difference at 10/15 minutes
   - Laning phase score calculation

2. **Player Rank Badge**: Requires League API endpoint per player

   - Already implemented: `fetch_rank_by_puuid()` exists
   - Need to call it for each participant in match detail
   - Consider caching strategy (rank doesn't change frequently)

3. **Achievement Badges**: Custom logic based on existing data
   - Data available: `doubleKills`, `tripleKills`, etc.
   - Need to implement ranking logic (7th, 3rd, "Victor", "Downfall")
   - Based on performance metrics vs other players in match

---

## Implementation Checklist

### Backend (services/api/app/services/riot_sync.py):

- [x] ~~Add champion level to participant fetch~~ - **Already available in Riot API response**
- [x] ~~Add item0-6 fields to participant fetch~~ - **Already available in Riot API response**
- [x] ~~Add summoner spell IDs to participant fetch~~ - **Already available in Riot API response**
- [x] ~~Add perks structure to participant fetch~~ - **Already available in Riot API response**
- [x] ~~Add remake detection flags to participant fetch~~ - **Already available in Riot API response**
- [ ] Add timeline API endpoint for laning stats (separate ticket - optional)
- [ ] Implement rank fetching for all match participants (use existing `fetch_rank_by_puuid`)
- [ ] Add achievement badge calculation logic

### Frontend (league-web/src):

- [ ] Create MatchOutcome enum in types
- [ ] Update Participant type with new fields
- [ ] Add QUEUE_ID_MAP constant
- [ ] Implement new utility functions in match-utils
- [ ] Refactor MatchCard into component modules
- [ ] Create placeholder images for items/spells/runes
- [ ] Implement outcome-based background colors
- [ ] Build team composition display
- [ ] Add advanced stats calculations
- [ ] Style achievement badges (with available data only)
- [ ] Format all time/duration displays
- [ ] Responsive layout testing

### Documentation:

- [ ] Document queue ID mappings
- [ ] Document achievement badge logic
- [ ] Update API contract in SHARED_PACKAGE.md if needed

---

## Notes

- **Remake Detection**: A remake is typically `gameEndedInEarlySurrender = true` AND `gameDuration < 300` (5 minutes)
- **Current Player Highlight**: Use `participant.puuid === user.puuid` to bold current player in team lists
- **Item CDN**: Use `https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{itemId}.png`
- **Spell CDN**: Use `https://ddragon.leagueoflegends.com/cdn/{version}/img/spell/Summoner{SpellName}.png`
- **Rune CDN**: Use `https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/{style}/{perkId}.png`

---

## Open Questions

1. Should we implement collapsible details panel (current functionality) or always show full card?
2. Do we want to cache timeline/rank data, or fetch on-demand?
3. What's the priority order for missing data implementation?
4. Should achievement badges be fully custom or based on Riot API challenge data?
