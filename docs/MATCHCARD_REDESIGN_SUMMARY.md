# MatchCard Redesign - Documentation Summary

## Overview

Analysis of screenshot showing target UI for League of Legends match cards, with comparison to current implementation and detailed implementation plan.

---

## Documentation Files

### 1. **MATCHCARD_UI_REDESIGN.md** - Complete Analysis

**Purpose:** Comprehensive breakdown of screenshot, data availability matrix, and implementation strategy

**Key sections:**

- Visual breakdown of all UI elements
- Three match states (Defeat/Remake/Victory) enum design
- Complete data availability matrix showing what we have vs. what's missing
- Type system updates needed
- Component structure recommendations
- Styling requirements with color palette
- Placeholder strategy for missing data

**Key finding:** 90% of data is already in our database - just needs TypeScript typing

### 2. **RIOT_API_PARTICIPANT_FIELDS.md** - Complete Field Reference

**Purpose:** Exhaustive documentation of every field available in Riot Match-V5 API participant objects

**Key sections:**

- 100+ fields categorized by type (champion, items, spells, damage, vision, etc.)
- Priority fields for redesign (critical/important/nice-to-have)
- Data Dragon CDN URLs for all asset types
- Summoner spell ID mappings
- Rune style path mappings

**Key finding:** All champion level, items, spells, perks, and multikill data is already available in our API responses

### 3. **MATCHCARD_ACTION_PLAN.md** - Step-by-Step Implementation

**Purpose:** Actionable task breakdown with time estimates and priority levels

**Key sections:**

- 7 implementation phases with hour estimates
- Detailed file structure for new component modules
- Props interfaces for each subcomponent
- CSS requirements and color palette
- Achievement badge logic specifications
- Test cases and success criteria
- Risk mitigation strategies

**Total estimated effort:** 15-22 hours for core features, 22-32 hours with optional enhancements

---

## Critical Insights

### ✅ Good News

1. **Backend is complete** - No new API integrations needed for core features
2. **Data is available** - Riot API returns all fields we need (items, spells, perks, levels, etc.)
3. **Storage works** - Full match payload stored in `Match.game_info` JSONB
4. **Frontend access exists** - Data already flows to components via API endpoints

### ⚠️ The Blocker

**TypeScript types are incomplete** - `Participant` type only defines ~15 fields, but Riot API returns 100+ fields

### 🎯 The Solution

**Frontend refactor:**

1. Update `src/lib/types/match.ts` with complete field definitions
2. Create new utility functions in `src/lib/match-utils.ts`
3. Restructure `MatchCard.tsx` into modular components
4. Apply new styling with outcome-based backgrounds
5. Add placeholder images for missing assets

---

## State Management: Match Outcomes

### Enum Definition

```typescript
enum MatchOutcome {
  DEFEAT = "defeat",
  REMAKE = "remake",
  VICTORY = "victory",
}
```

### Visual Treatment

- **DEFEAT**: Dark red background (`#4a2828`)
- **REMAKE**: Gray background (`#3a3a3a`)
- **VICTORY**: Blue background (`#2c4a6e`)

### Detection Logic

```typescript
function getMatchOutcome(participant: Participant): MatchOutcome {
  if (
    participant.gameEndedInEarlySurrender ||
    participant.teamEarlySurrendered
  ) {
    return MatchOutcome.REMAKE;
  }
  return participant.win ? MatchOutcome.VICTORY : MatchOutcome.DEFEAT;
}
```

---

## Component Architecture

### Current (Single File)

```
MatchCard.tsx (103 lines)
  ├─ Header (Match ID + Champion Name + Win/Loss)
  ├─ Summary (KDA, CS/min, Lane, Role)
  ├─ Toggle Button (Show/Hide Details)
  └─ Details Panel (Kills, Deaths, Assists, Gold, Duration, Queue)
```

### Proposed (Modular)

```
MatchCard/ (300-400 lines total, split across 10 files)
  ├─ MatchCard.tsx (Main orchestrator, ~50 lines)
  ├─ MatchCardHeader.tsx (Queue + Time, ~30 lines)
  ├─ MatchCardOutcome.tsx (Outcome label + Duration, ~30 lines)
  ├─ MatchCardChampion.tsx (Portrait + Level badge, ~40 lines)
  ├─ MatchCardStats.tsx (K/D/A + KDA ratio, ~30 lines)
  ├─ MatchCardItems.tsx (7 item slots, ~50 lines)
  ├─ MatchCardSpells.tsx (2 spells + 2 runes, ~50 lines)
  ├─ MatchCardBadges.tsx (Achievement badges, ~60 lines)
  ├─ MatchCardTeams.tsx (10 players, ~60 lines)
  └─ MatchCardAdvanced.tsx (Laning/P/Kill/CS/Rank, ~40 lines)
```

**Benefits:**

- Easier testing (each component isolated)
- Better code organization (single responsibility)
- Reusability (e.g., MatchCardItems could be used elsewhere)
- Performance optimization (can memo individual components)

---

## Data Mapping: What Goes Where

| Screenshot Element  | Data Source                                      | Component         | Status                |
| ------------------- | ------------------------------------------------ | ----------------- | --------------------- |
| "Ranked Solo/Duo"   | `detail.info.queueId` → map to string            | MatchCardHeader   | ✅ Data available     |
| "1 day ago"         | `match.gameCreation` → format relative           | MatchCardHeader   | ✅ Data available     |
| "Defeat" label      | `participant.win` + `gameEndedInEarlySurrender`  | MatchCardOutcome  | ✅ Data available     |
| "35m 44s"           | `detail.info.gameDuration` → format              | MatchCardOutcome  | ✅ Data available     |
| Champion portrait   | `champion.imageUrl`                              | MatchCardChampion | ✅ Data available     |
| Level badge "15"    | `participant.champLevel`                         | MatchCardChampion | ⚠️ Needs typing       |
| "8 / 9 / 7"         | `participant.kills/deaths/assists`               | MatchCardStats    | ✅ Data available     |
| "1.67:1 KDA"        | Computed from K/D/A                              | MatchCardStats    | ✅ Data available     |
| 6 item slots        | `participant.item0-5`                            | MatchCardItems    | ⚠️ Needs typing       |
| Trinket slot        | `participant.item6`                              | MatchCardItems    | ⚠️ Needs typing       |
| Summoner spells     | `participant.summoner1Id/2Id`                    | MatchCardSpells   | ⚠️ Needs typing       |
| Keystone rune       | `participant.perks.styles[0].selections[0].perk` | MatchCardSpells   | ⚠️ Needs typing       |
| Secondary rune      | `participant.perks.styles[1].style`              | MatchCardSpells   | ⚠️ Needs typing       |
| "Double Kill" badge | `participant.doubleKills > 0`                    | MatchCardBadges   | ⚠️ Needs typing       |
| "7th" badge         | Sort by damage, get position                     | MatchCardBadges   | ⚠️ Needs logic        |
| "Downfall" badge    | Custom logic (high deaths, low KDA)              | MatchCardBadges   | ⚠️ Needs logic        |
| Player list         | `detail.info.participants[]`                     | MatchCardTeams    | ✅ Data available     |
| "damanjr" (bold)    | `participant.puuid === user.puuid`               | MatchCardTeams    | ✅ Data available     |
| "P/Kill 60%"        | `(K+A) / teamKills * 100`                        | MatchCardAdvanced | ⚠️ Needs logic        |
| "CS 103 (5)"        | `totalMinionsKilled + neutralMinionsKilled`      | MatchCardAdvanced | ✅ Data available     |
| "Silver 2"          | Rank API call                                    | MatchCardAdvanced | ❌ Missing (optional) |
| "Laning 43 : 57"    | Timeline API call                                | MatchCardAdvanced | ❌ Missing (optional) |

**Legend:**

- ✅ Data available: Already in types, ready to use
- ⚠️ Needs typing: Data available in API response, needs TypeScript definition
- ⚠️ Needs logic: Data available, needs calculation/processing function
- ❌ Missing: Requires new API endpoint (optional feature)

---

## Placeholder Strategy

For any missing or unavailable data, follow this pattern:

### Text Data

```typescript
const champLevel = participant?.champLevel ?? "missing";
const rank = "missing"; // Until rank API integrated
const laningScore = "missing"; // Until timeline API integrated
```

### Image Data

```typescript
// Fallback chain: try CDN → try local → use placeholder
<img
  src={getItemUrl(itemId)}
  onError={(e) => {
    e.target.src = "/placeholders/placeholder-item.png";
  }}
  alt={`Item ${itemId}`}
/>
```

### Badges (Don't show "missing")

```typescript
// Only render badges if data is available
{
  participant.doubleKills > 0 && <Badge type="multikill">Double Kill</Badge>;
}
{
  participant.pentaKills > 0 && <Badge type="multikill">Penta Kill</Badge>;
}

// Don't do this:
{
  participant.tripleKills ?? <Badge>missing</Badge>;
} // ❌ Bad
```

---

## Asset Management

### Required Placeholders

Create in `league-web/public/placeholders/`:

- `placeholder-item.png` (64x64px)
- `placeholder-spell.png` (48x48px)
- `placeholder-rune.png` (48x48px)
- `placeholder-champion.png` (128x128px)

### CDN URLs (Data Dragon)

- Items: `https://ddragon.leagueoflegends.com/cdn/14.1.1/img/item/{itemId}.png`
- Spells: `https://ddragon.leagueoflegends.com/cdn/14.1.1/img/spell/Summoner{SpellName}.png`
- Runes: `https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/{style}/{perkId}.png`

### Version Management

```typescript
// Use latest patch version
const DDragonVersion = "14.1.1"; // Update periodically or fetch from API

// Or make configurable
const getAssetUrl = (
  type: "item" | "spell" | "rune",
  id: number,
  version = DDragonVersion
) => {
  // ...
};
```

---

## Testing Checklist

### Visual States

- [ ] Defeat card shows red background
- [ ] Remake card shows gray background
- [ ] Victory card shows blue background
- [ ] Champion level badge displays correctly
- [ ] K/D/A uses color coding (green/red/blue)
- [ ] Items display in correct slots
- [ ] Summoner spells show correct icons
- [ ] Keystone + secondary rune show correct icons

### Data Handling

- [ ] "missing" displays when champLevel unavailable
- [ ] Placeholder images load when item ID is 0
- [ ] Remake detection works (short game + early surrender)
- [ ] Kill participation calculates correctly
- [ ] Achievement badges only show when applicable

### Layout

- [ ] Card layout matches screenshot
- [ ] All 10 players visible
- [ ] Current player highlighted (bold)
- [ ] Responsive on mobile (single column)
- [ ] Responsive on tablet (2 columns)
- [ ] Responsive on desktop (3 columns)

### Error Handling

- [ ] Handles missing participant data gracefully
- [ ] Handles missing match detail gracefully
- [ ] Handles image load failures gracefully
- [ ] No console errors
- [ ] No TypeScript warnings

---

## Future Enhancements (Optional)

### Timeline API Integration

**Effort:** 4-6 hours  
**Benefit:** Laning phase stats (CS diff, gold diff at 10/15 min)  
**Endpoint:** `/lol/match/v5/matches/{matchId}/timeline`

**Implementation:**

1. Add new method to `RiotApiClient`
2. Store timeline data in separate column or nested in `game_info`
3. Create cache strategy (timelines are immutable, can cache forever)
4. Calculate laning score from CS/gold differences
5. Display in `MatchCardAdvanced` component

### Per-Player Rank Badges

**Effort:** 3-4 hours  
**Benefit:** Show rank for all 10 players in match  
**Endpoint:** `/lol/league/v4/entries/by-summoner/{summonerId}`

**Implementation:**

1. Batch fetch ranks for all participants
2. Cache aggressively (rank changes slowly, 1-hour TTL)
3. Handle unranked players gracefully
4. Display as badge in `MatchCardAdvanced` or `MatchCardTeams`

### Live Game Integration

**Effort:** 8-10 hours  
**Benefit:** Show current live games for user  
**Endpoint:** `/lol/spectator/v5/active-games/by-summoner/{summonerId}`

**Implementation:**

1. Add live game endpoint to API
2. Create separate `LiveGameCard` component (similar structure to MatchCard)
3. Poll for updates every 30 seconds
4. Show real-time stats (current gold, CS, items)

---

## Open Questions

1. **Should collapsed details panel be kept?**

   - Current: Card has "Show/Hide details" toggle
   - Screenshot: Appears to be always-expanded
   - **Recommendation:** Remove toggle, always show full card (matches screenshot)

2. **What priority for optional features?**

   - Timeline API (laning stats)?
   - Rank badges for all players?
   - Live game support?
   - **Recommendation:** Ship core redesign first, add enhancements in separate PRs

3. **How to handle very old matches?**

   - Data Dragon version changes over time
   - Old items may not exist in current CDN
   - **Recommendation:** Store patch version in match record, use for CDN URLs

4. **Performance optimization strategy?**
   - Rendering 20 matches at once = 200 champion icons + 140 items
   - **Recommendation:** Implement virtual scrolling if > 10 matches, use React.memo

---

## Success Metrics

### Before (Current Implementation)

- Shows: Champion name, win/loss, KDA, CS/min, lane, role
- Lines of code: 103
- Components: 1 monolithic file
- Assets displayed: 1 (champion portrait)
- Data fields used: ~10

### After (Target Implementation)

- Shows: Queue, time, outcome, duration, champion, level, K/D/A, KDA, 7 items, 2 spells, 2 runes, badges, 10 players, advanced stats
- Lines of code: ~400 (split across 10 files)
- Components: 10 modular files
- Assets displayed: ~20 (champion + items + spells + runes)
- Data fields used: ~30

### Quality Metrics

- ✅ TypeScript type coverage: 100%
- ✅ Null safety: Optional chaining everywhere
- ✅ Error boundaries: Image fallbacks implemented
- ✅ Performance: React.memo for expensive components
- ✅ Accessibility: Alt text on all images
- ✅ Responsive: Mobile/tablet/desktop layouts

---

## Quick Start Guide

To begin implementation:

1. **Read in order:**

   - This summary (you are here)
   - `MATCHCARD_UI_REDESIGN.md` (detailed analysis)
   - `MATCHCARD_ACTION_PLAN.md` (step-by-step tasks)

2. **Reference as needed:**

   - `RIOT_API_PARTICIPANT_FIELDS.md` (field definitions)

3. **Start coding:**

   - Phase 1: Update types in `src/lib/types/match.ts`
   - Phase 2: Add utilities in `src/lib/match-utils.ts`
   - Phase 3: Restructure components in `src/components/MatchCard/`

4. **Test frequently:**
   - After each phase, verify in browser
   - Check network tab to confirm data availability
   - Test with different match types (win/loss/remake)

---

## Related Files

### Current Implementation

- `league-web/src/components/MatchCard.tsx` (to be refactored)
- `league-web/src/components/MatchCard.module.css` (to be expanded)
- `league-web/src/lib/types/match.ts` (to be updated)
- `league-web/src/lib/match-utils.ts` (to be expanded)

### Backend (Reference Only)

- `services/api/app/services/riot_sync.py` (match fetching)
- `services/api/app/services/riot_api_client.py` (Riot API client)
- `services/api/app/models/match.py` (database model)

### Documentation

- `MATCHCARD_UI_REDESIGN.md` (this file's companion)
- `RIOT_API_PARTICIPANT_FIELDS.md` (field reference)
- `MATCHCARD_ACTION_PLAN.md` (implementation guide)

---

## Contact & Questions

For questions about:

- **Design decisions**: See `MATCHCARD_UI_REDESIGN.md`
- **Data availability**: See `RIOT_API_PARTICIPANT_FIELDS.md`
- **Implementation steps**: See `MATCHCARD_ACTION_PLAN.md`
- **Everything else**: Check this summary first

---

_Last updated: 2026-02-04_  
_Based on screenshot analysis showing Defeat/Remake/Victory match cards_
