# MatchCard UI Redesign - Action Plan

## Quick Status

✅ **Data is already available** - Riot API returns everything we need  
⚠️ **Frontend types are incomplete** - Can't access the data in components  
🎯 **This is a frontend refactor** - 90% of work is in league-web/src

---

## Phase 1: Type System (1-2 hours)

**File:** `league-web/src/lib/types/match.ts`

### Tasks:

1. Add match outcome enum
2. Expand Participant type with 30+ missing fields
3. Add ParticipantPerks type
4. Add queue ID mapping constant

**Reference:** See `RIOT_API_PARTICIPANT_FIELDS.md` for complete field list

**Priority fields to add:**

```typescript
champLevel: number;
item0-6: number;
summoner1Id, summoner2Id: number;
perks: ParticipantPerks;
doubleKills, tripleKills, quadraKills, pentaKills: number;
gameEndedInEarlySurrender, teamEarlySurrendered: boolean;
visionScore: number;
totalDamageDealtToChampions: number;
```

---

## Phase 2: Utility Functions (2-3 hours)

**File:** `league-web/src/lib/match-utils.ts`

### New functions needed:

```typescript
getMatchOutcome(participant) -> MatchOutcome enum
formatGameDuration(seconds) -> "Xm Ys"
formatRelativeTime(timestamp) -> "X days ago"
getQueueName(queueId) -> "Ranked Solo/Duo"
calculateKillParticipation(participant, allParticipants) -> number
getAlliedTeam(participants, currentParticipant) -> Participant[]
getEnemyTeam(participants, currentParticipant) -> Participant[]
getItemUrl(itemId, version) -> string
getSummonerSpellUrl(spellId, version) -> string
getKeystoneUrl(perkId, styleId) -> string
```

**Add mappings:**

- Queue ID → Queue Name
- Summoner Spell ID → Spell Name
- Rune Style ID → Style Path

---

## Phase 3: Component Restructuring (4-6 hours)

### Current structure (single file):

```
components/
  MatchCard.tsx
  MatchCard.module.css
```

### New structure (modular):

```
components/
  MatchCard/
    MatchCard.tsx              // Main orchestrator
    MatchCardHeader.tsx        // Queue type + time ago
    MatchCardOutcome.tsx       // Defeat/Remake/Victory label + duration
    MatchCardChampion.tsx      // Champion portrait with level badge
    MatchCardStats.tsx         // K/D/A large display + KDA ratio
    MatchCardItems.tsx         // 6 items + trinket
    MatchCardSpells.tsx        // 2 summoner spells + keystone + secondary rune
    MatchCardBadges.tsx        // Achievement badges (Double Kill, 7th, etc.)
    MatchCardTeams.tsx         // 10 player list (allied + enemy)
    MatchCardAdvanced.tsx      // Laning, P/Kill, CS, Rank
    MatchCard.module.css       // Shared styles
```

### Props for each subcomponent:

```typescript
// MatchCardHeader
{ queueId: number, gameCreation: number }

// MatchCardOutcome
{ outcome: MatchOutcome, duration: number }

// MatchCardChampion
{ championImageUrl: string, championName: string, level: number }

// MatchCardStats
{ kills: number, deaths: number, assists: number, kdaRatio: number }

// MatchCardItems
{ items: [number, number, number, number, number, number, number] }

// MatchCardSpells
{ summoner1Id: number, summoner2Id: number, keystonePerk: number, secondaryStyle: number }

// MatchCardBadges
{ doubleKills: number, tripleKills: number, quadraKills: number, pentaKills: number,
  rankPosition: number | null, performanceRating: 'victor' | 'downfall' | null }

// MatchCardTeams
{ allParticipants: Participant[], currentParticipant: Participant, currentUserPuuid: string }

// MatchCardAdvanced
{ laningScore: string, killParticipation: number, csTotal: number, csAtTime: number | null,
  rank: string | null }
```

---

## Phase 4: Styling (3-4 hours)

**File:** `league-web/src/components/MatchCard/MatchCard.module.css`

### Key CSS features:

1. **Outcome-based backgrounds:**

   - Defeat: `#4a2828` (dark red)
   - Remake: `#3a3a3a` (gray)
   - Victory: `#2c4a6e` (blue)

2. **Stat color coding:**

   - Kills: `#4ade80` (green)
   - Deaths: `#f87171` (red)
   - Assists: `#60a5fa` (blue)

3. **Champion portrait:**

   - Circular border
   - Level badge overlay (bottom-right)

4. **Item grid:**

   - 7 square slots (6 items + trinket)
   - Gray placeholder for empty slots

5. **Achievement badges:**

   - Rounded pill shape
   - Color-coded by type (red for multikills, purple for rank, etc.)

6. **Team composition:**

   - Two columns (allied left, enemy right)
   - Champion icons + summoner names
   - Bold current player

7. **Responsive layout:**
   - 3-column grid: [Left info | Center champion/items | Right teams/stats]
   - Collapse to single column on mobile

---

## Phase 5: Placeholder Assets (1 hour)

**Create placeholder images in:** `league-web/public/placeholders/`

### Files needed:

```
placeholder-item.png       // Gray square with "?" for missing items
placeholder-spell.png      // Gray square with "?" for missing spells
placeholder-rune.png       // Gray square with "?" for missing runes
placeholder-champion.png   // Gray circle with "?" for missing champion portraits
```

**Dimensions:**

- Items: 64x64px
- Spells: 48x48px
- Runes: 48x48px
- Champion: 128x128px

**Style:** Dark gray background (#2a2a2a), light gray "?" text (#888888)

---

## Phase 6: Achievement Badge Logic (2-3 hours)

**File:** `league-web/src/lib/achievement-utils.ts`

### Badge types:

1. **Multikill badges:**

   - "Double Kill" (red) if `doubleKills > 0`
   - "Triple Kill" (red) if `tripleKills > 0`
   - "Quadra Kill" (red) if `quadraKills > 0`
   - "Penta Kill" (gold) if `pentaKills > 0`

2. **Rank badges:**

   - Sort all participants by total damage to champions
   - Display position: "7th", "3rd", "1st", etc.
   - Color: purple

3. **Performance badges:**
   - "Victor" (blue) if:
     - Win = true AND
     - Damage > team average by 20%+ OR
     - KDA > 5.0
   - "Downfall" (orange) if:
     - Win = false AND
     - Deaths > 10 OR
     - KDA < 1.0

**Functions:**

```typescript
getMultikillBadges(participant: Participant) -> Badge[]
getRankBadge(participant: Participant, allParticipants: Participant[]) -> Badge | null
getPerformanceBadge(participant: Participant, teamParticipants: Participant[]) -> Badge | null
```

---

## Phase 7: Integration & Testing (2-3 hours)

### Integration steps:

1. Replace old MatchCard with new modular version
2. Test with different match outcomes (defeat, remake, victory)
3. Test with missing data (ensure "missing" displays correctly)
4. Test with incomplete Riot API responses
5. Verify placeholder images load correctly
6. Test responsive layout on mobile/tablet/desktop

### Test cases:

- ✅ Remake game (short duration, early surrender)
- ✅ Victory with Penta kill
- ✅ Defeat with no items (testing placeholders)
- ✅ Match with missing perks data
- ✅ Match with all 10 players shown correctly
- ✅ Current player highlighted in team list

---

## Optional: Enhanced Features (Future)

### Timeline API Integration (separate ticket):

**Endpoint:** `/lol/match/v5/matches/{matchId}/timeline`

**Data available:**

- CS difference at 10/15 minutes
- Gold difference at 10/15 minutes
- Lane opponent identification
- Laning phase score calculation

**Effort:** 4-6 hours (new API client method, new data model, cache strategy)

### Rank Badge per Player (separate ticket):

**Endpoint:** `/lol/league/v4/entries/by-summoner/{summonerId}`

**Implementation:**

- Fetch rank for each participant
- Cache aggressively (rank changes slowly)
- Display as badge in advanced stats panel

**Effort:** 3-4 hours (batch fetching, cache strategy, UI integration)

---

## Estimated Total Effort

| Phase                      | Hours           | Priority |
| -------------------------- | --------------- | -------- |
| 1. Type System             | 1-2             | Critical |
| 2. Utility Functions       | 2-3             | Critical |
| 3. Component Restructuring | 4-6             | Critical |
| 4. Styling                 | 3-4             | Critical |
| 5. Placeholder Assets      | 1               | High     |
| 6. Achievement Badges      | 2-3             | High     |
| 7. Integration & Testing   | 2-3             | Critical |
| **Total Core Work**        | **15-22 hours** |          |
| 8. Timeline API (optional) | 4-6             | Medium   |
| 9. Rank Badges (optional)  | 3-4             | Medium   |
| **Total with Optional**    | **22-32 hours** |          |

---

## Risk Mitigation

### Potential blockers:

1. **Riot API data inconsistencies:** Some fields may be null/undefined

   - **Solution:** Use optional chaining and nullish coalescing everywhere
   - **Example:** `participant?.champLevel ?? 'missing'`

2. **Image loading failures:** CDN downtime or missing assets

   - **Solution:** Implement error boundaries and fallback to placeholders
   - **Example:** `<img onError={(e) => e.target.src = '/placeholders/item.png'} />`

3. **Performance issues:** Rendering 10 players with images

   - **Solution:** Use React.memo for subcomponents, lazy load images
   - **Example:** `const MatchCardTeams = React.memo(({ participants }) => ...)`

4. **Type mismatches:** API response doesn't match TypeScript types
   - **Solution:** Add runtime validation with Zod or similar
   - **Example:** `const ParticipantSchema = z.object({ ... })`

---

## Success Criteria

✅ Match cards display all three states (defeat/remake/victory) with correct colors  
✅ Champion portrait shows level badge  
✅ K/D/A displayed prominently on card front  
✅ Item build visible (6 items + trinket)  
✅ Summoner spells and keystone rune visible  
✅ Achievement badges shown when applicable  
✅ All 10 players listed with champion icons  
✅ Current player highlighted in bold  
✅ Advanced stats panel shows P/Kill and CS  
✅ "missing" displayed for unavailable data  
✅ Placeholder images used for missing assets  
✅ Responsive layout works on all screen sizes  
✅ No console errors or TypeScript warnings

---

## Next Steps

1. Read this plan
2. Start with Phase 1 (types)
3. Validate types with actual API response (check network tab or logs)
4. Proceed sequentially through phases
5. Commit after each phase for easy rollback
6. Test continuously during development
