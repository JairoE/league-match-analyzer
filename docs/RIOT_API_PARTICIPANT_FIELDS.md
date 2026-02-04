# Riot API Participant Fields Reference

## Complete Participant Object Structure

Based on Riot's Match-V5 API documentation, each participant object in `match.info.participants[]` contains the following fields:

### ✅ Fields We Already Use

```typescript
{
  puuid: string,
  summonerName: string,
  championId: number,
  championName: string,
  kills: number,
  deaths: number,
  assists: number,
  win: boolean,
  teamId: number,
  lane: string,
  role: string,
  totalMinionsKilled: number,
  neutralMinionsKilled: number,
  goldEarned: number
}
```

### 🆕 Fields Available But Not Typed (NEEDED FOR UI REDESIGN)

#### Champion & Level

```typescript
{
  champLevel: number,              // Champion level at end of game (e.g., 15)
  champExperience: number          // Total XP earned
}
```

#### Items (7 slots: 6 items + trinket)

```typescript
{
  item0: number,                   // Item slot 0 (item ID, 0 = empty)
  item1: number,                   // Item slot 1
  item2: number,                   // Item slot 2
  item3: number,                   // Item slot 3
  item4: number,                   // Item slot 4
  item5: number,                   // Item slot 5
  item6: number                    // Trinket slot
}
```

#### Summoner Spells

```typescript
{
  summoner1Id: number,             // First summoner spell ID (e.g., 4 = Flash)
  summoner2Id: number,             // Second summoner spell ID
  summoner1Casts: number,          // Times spell 1 was cast
  summoner2Casts: number           // Times spell 2 was cast
}
```

#### Perks/Runes

```typescript
{
  perks: {
    statPerks: {
      defense: number,             // Defense stat perk ID
      flex: number,                // Flex stat perk ID
      offense: number              // Offense stat perk ID
    },
    styles: [
      {
        description: string,       // "primaryStyle" or "subStyle"
        selections: [
          {
            perk: number,          // Rune ID
            var1: number,          // Rune-specific variable 1
            var2: number,          // Rune-specific variable 2
            var3: number           // Rune-specific variable 3
          }
        ],
        style: number              // Rune tree ID (e.g., 8000 = Precision)
      }
    ]
  }
}
```

#### Kill Streaks & Multikills

```typescript
{
  doubleKills: number,             // Number of double kills
  tripleKills: number,             // Number of triple kills
  quadraKills: number,             // Number of quadra kills
  pentaKills: number,              // Number of penta kills
  killingSprees: number,           // Number of killing sprees (3+ without dying)
  largestKillingSpree: number,     // Longest killing spree
  largestMultiKill: number         // Largest multikill (2=double, 3=triple, etc.)
}
```

#### Damage Dealt

```typescript
{
  totalDamageDealt: number,                    // Total damage (all types)
  totalDamageDealtToChampions: number,         // Damage to champions only
  physicalDamageDealt: number,                 // Physical damage (all)
  physicalDamageDealtToChampions: number,      // Physical damage to champions
  magicDamageDealt: number,                    // Magic damage (all)
  magicDamageDealtToChampions: number,         // Magic damage to champions
  trueDamageDealt: number,                     // True damage (all)
  trueDamageDealtToChampions: number,          // True damage to champions
  largestCriticalStrike: number,               // Largest crit damage
  damageDealtToObjectives: number,             // Damage to turrets/dragons/baron
  damageDealtToTurrets: number,                // Damage to turrets only
  damageSelfMitigated: number                  // Damage mitigated by shields/resistances
}
```

#### Damage Taken

```typescript
{
  totalDamageTaken: number,                    // Total damage taken
  physicalDamageTaken: number,                 // Physical damage taken
  magicDamageTaken: number,                    // Magic damage taken
  trueDamageTaken: number                      // True damage taken
}
```

#### Healing & Shielding

```typescript
{
  totalHeal: number,                           // Total healing done
  totalHealsOnTeammates: number,               // Healing on allies
  totalDamageShieldedOnTeammates: number,      // Shielding on allies
  totalUnitsHealed: number                     // Number of units healed
}
```

#### Vision

```typescript
{
  visionScore: number,                         // Overall vision score
  wardsPlaced: number,                         // Wards placed
  wardsKilled: number,                         // Enemy wards destroyed
  visionWardsBoughtInGame: number,             // Control wards purchased
  detectorWardsPlaced: number,                 // Control wards placed
  sightWardsBoughtInGame: number               // (Deprecated - always 0)
}
```

#### Objectives

```typescript
{
  objectivesStolen: number,                    // Dragons/barons stolen
  objectivesStolenAssists: number,             // Assists on stolen objectives
  turretKills: number,                         // Turrets destroyed
  turretTakedowns: number,                     // Turret kill participation
  inhibitorKills: number,                      // Inhibitors destroyed
  inhibitorTakedowns: number,                  // Inhibitor kill participation
  dragonKills: number,                         // Dragons killed
  baronKills: number                           // Barons killed
}
```

#### Gold & Economy

```typescript
{
  goldEarned: number,                          // Total gold earned
  goldSpent: number,                           // Gold spent on items
  totalMinionsKilled: number,                  // Lane minions killed
  neutralMinionsKilled: number                 // Jungle monsters killed
}
```

#### Time Stats

```typescript
{
  timePlayed: number,                          // Seconds played (includes loading)
  longestTimeSpentLiving: number,              // Longest life duration (seconds)
  timeCCingOthers: number,                     // Time spent CCing enemies (seconds)
  totalTimeSpentDead: number,                  // Total time dead (seconds)
  totalTimeCCDealt: number                     // Total CC duration dealt (seconds)
}
```

#### Game End State

```typescript
{
  gameEndedInEarlySurrender: boolean,          // True if remake/early FF
  gameEndedInSurrender: boolean,               // True if team surrendered
  teamEarlySurrendered: boolean                // True if team remade
}
```

#### First Blood / Events

```typescript
{
  firstBloodKill: boolean,                     // Got first blood
  firstBloodAssist: boolean,                   // Assisted first blood
  firstTowerKill: boolean,                     // Destroyed first tower
  firstTowerAssist: boolean                    // Assisted first tower
}
```

#### Consumables

```typescript
{
  consumablesPurchased: number,                // Potions/elixirs bought
  itemsPurchased: number                       // Total items purchased
}
```

#### Miscellaneous

```typescript
{
  nexusKills: number,                          // Nexus kills (usually 0 or 1)
  nexusTakedowns: number,                      // Nexus participation
  nexusLost: number,                           // Own nexus destroyed
  spell1Casts: number,                         // Q ability casts
  spell2Casts: number,                         // W ability casts
  spell3Casts: number,                         // E ability casts
  spell4Casts: number,                         // R ability casts
  participantId: number,                       // Participant ID (1-10)
  profileIcon: number,                         // Profile icon ID
  riotIdGameName: string,                      // Riot ID game name
  riotIdTagline: string,                       // Riot ID tagline
  summonerId: string,                          // Summoner ID
  summonerLevel: number                        // Account level
}
```

---

## Priority Fields for MatchCard Redesign

### Critical (Must Have)

1. `champLevel` - Display on champion portrait
2. `item0` through `item6` - Item build display
3. `summoner1Id`, `summoner2Id` - Summoner spell icons
4. `perks.styles[0].selections[0].perk` - Keystone rune icon
5. `perks.styles[1].style` - Secondary rune tree icon
6. `gameEndedInEarlySurrender` - Remake detection
7. `visionScore` - Advanced stats panel
8. `totalDamageDealtToChampions` - Damage calculations

### Important (Should Have)

9. `doubleKills`, `tripleKills`, etc. - Achievement badges
10. `largestMultiKill` - Achievement badges
11. `killingSprees` - Achievement badges
12. Kill participation calculation (requires team totals)

### Nice to Have

13. `timeCCingOthers` - Advanced stats
14. `goldEarned` - Already used but can be displayed more prominently
15. `turretKills`, `inhibitorKills` - Objective stats

---

## Data Dragon URLs for Assets

### Items

```
https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{itemId}.png
Example: https://ddragon.leagueoflegends.com/cdn/14.1.1/img/item/3153.png
```

### Summoner Spells

```
https://ddragon.leagueoflegends.com/cdn/{version}/img/spell/Summoner{SpellName}.png
Example: https://ddragon.leagueoflegends.com/cdn/14.1.1/img/spell/SummonerFlash.png
```

**Spell ID to Name Mapping:**

```typescript
const SUMMONER_SPELL_MAP: Record<number, string> = {
  1: "Boost", // Cleanse
  3: "Exhaust",
  4: "Flash",
  6: "Haste", // Ghost
  7: "Heal",
  11: "Smite",
  12: "Teleport",
  13: "Mana", // Clarity (ARAM only)
  14: "Dot", // Ignite
  21: "Barrier",
  30: "PoroRecall", // (ARAM)
  31: "PoroThrow", // (ARAM Mark/Dash)
  32: "Snowball", // (ARAM Mark/Dash - renamed)
  39: "UltBook", // (Ultimate Spellbook)
  54: "Placeholder", // (Placeholder)
  55: "Placeholder", // (Placeholder)
};
```

### Runes

```
https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/{stylePath}/{perkId}.png
```

**Rune Style Paths:**

```typescript
const RUNE_STYLE_PATHS: Record<number, string> = {
  8000: "Precision", // Precision tree
  8100: "Domination", // Domination tree
  8200: "Sorcery", // Sorcery tree
  8300: "Inspiration", // Inspiration tree
  8400: "Resolve", // Resolve tree
};
```

**Example Keystone URLs:**

```
Electrocute (8112): https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Domination/Electrocute/Electrocute.png
Press the Attack (8005): https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Precision/PressTheAttack/PressTheAttack.png
```

---

## Implementation Notes

1. **All these fields are already in the API response** - stored in `Match.game_info` JSONB
2. **TypeScript typing is the blocker** - frontend can't access undefined properties
3. **No backend changes needed** - just update `src/lib/types/match.ts`
4. **Riot API version**: Currently using Match-V5 (stable, production-ready)
5. **Rate limits**: Already handled by existing `RiotApiClient` implementation
