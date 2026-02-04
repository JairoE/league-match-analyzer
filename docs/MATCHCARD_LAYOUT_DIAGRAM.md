# MatchCard Layout Diagram

## Desktop Layout (3-column grid)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ MATCHCARD CONTAINER - Outcome-based background (Red/Gray/Blue)                     │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────┬──────────────────────────────┬──────────────────────────┐│
│  │   LEFT COLUMN       │      CENTER COLUMN           │    RIGHT COLUMN          ││
│  │   (Metadata)        │      (Champion & Build)      │    (Teams & Stats)       ││
│  │                     │                              │                          ││
│  │ ┌─────────────────┐ │  ┌────────┐                 │  ┌──────────────────────┐││
│  │ │ MatchCardHeader │ │  │        │ Champion        │  │  MatchCardTeams      │││
│  │ ├─────────────────┤ │  │   🎮   │ Portrait        │  │  ┌────────────────┐  │││
│  │ │ Ranked Solo/Duo │ │  │        │ (Circular)      │  │  │ Allied Team    │  │││
│  │ │ 1 day ago       │ │  │ Level  │                 │  │  │ ┌──┬─────────┐ │  │││
│  │ └─────────────────┘ │  │  [15]  │                 │  │  │ │🎮│Player 1 │ │  │││
│  │                     │  └────────┘                 │  │  │ │🎮│Player 2 │ │  │││
│  │ ┌─────────────────┐ │                             │  │  │ │🎮│damanjr  │ │  │││ ← Bold
│  │ │MatchCardOutcome │ │  ┌──┬──┐                   │  │  │ │🎮│Player 4 │ │  │││
│  │ ├─────────────────┤ │  │⚡│🔥│  Summoner          │  │  │ │🎮│Player 5 │ │  │││
│  │ │ DEFEAT          │ │  └──┴──┘  Spells           │  │  │ └──┴─────────┘ │  │││
│  │ │ 35m 44s         │ │                             │  │  │                │  │││
│  │ └─────────────────┘ │  ┌──┬──┐                   │  │  │ Enemy Team     │  │││
│  │                     │  │🌲│⚡│  Runes             │  │  │ ┌──┬─────────┐ │  │││
│  │                     │  └──┴──┘  (Key + Secondary)│  │  │ │🎮│Enemy 1  │ │  │││
│  │                     │                             │  │  │ │🎮│Enemy 2  │ │  │││
│  │                     │  ┌───────────────────────┐  │  │  │ │🎮│Enemy 3  │ │  │││
│  │                     │  │ MatchCardStats        │  │  │  │ │🎮│Enemy 4  │ │  │││
│  │                     │  ├───────────────────────┤  │  │  │ │🎮│Enemy 5  │ │  │││
│  │                     │  │   8  /  9  /  7       │  │  │  │ └──┴─────────┘ │  │││
│  │                     │  │  Kills Deaths Assists │  │  │  └────────────────┘  │││
│  │                     │  │   (Color Coded)       │  │  │                      │││
│  │                     │  │                       │  │  │  ┌──────────────────┐││
│  │                     │  │    1.67:1 KDA         │  │  │  │MatchCardAdvanced│││
│  │                     │  └───────────────────────┘  │  │  ├──────────────────┤││
│  │                     │                             │  │  │ Laning: 43 : 57  │││
│  │                     │  ┌───────────────────────┐  │  │  │ P/Kill: 60%      │││
│  │                     │  │ MatchCardItems        │  │  │  │ CS: 103 (5)      │││
│  │                     │  ├───────────────────────┤  │  │  │ Rank: Silver 2   │││
│  │                     │  │ ┌──┬──┬──┬──┬──┬──┐  │  │  │  └──────────────────┘││
│  │                     │  │ │📦│📦│📦│📦│📦│📦│  │  │  │                      │││
│  │                     │  │ └──┴──┴──┴──┴──┴──┘  │  │  │                      │││
│  │                     │  │        ┌──┐           │  │  │                      │││
│  │                     │  │        │👁️│ Trinket   │  │  │                      │││
│  │                     │  │        └──┘           │  │  │                      │││
│  │                     │  └───────────────────────┘  │  │                      │││
│  │                     │                             │  │                      │││
│  │                     │  ┌───────────────────────┐  │  │                      │││
│  │                     │  │ MatchCardBadges       │  │  │                      │││
│  │                     │  ├───────────────────────┤  │  │                      │││
│  │                     │  │ [Double Kill] [7th]   │  │  │                      │││
│  │                     │  │ [Downfall]            │  │  │                      │││
│  │                     │  └───────────────────────┘  │  │                      │││
│  │                     │                             │  │                      │││
│  └─────────────────────┴──────────────────────────────┴──────────────────────────┘│
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ [Expand/Collapse Button] - Optional for future detailed stats              │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Hierarchy

```
MatchCard (Main Container)
│
├─ Left Column
│  ├─ MatchCardHeader
│  │  ├─ Queue Type ("Ranked Solo/Duo")
│  │  └─ Time Ago ("1 day ago")
│  │
│  └─ MatchCardOutcome
│     ├─ Outcome Label ("DEFEAT" / "REMAKE" / "VICTORY")
│     └─ Duration ("35m 44s")
│
├─ Center Column
│  ├─ MatchCardChampion
│  │  ├─ Champion Portrait (circular image)
│  │  └─ Level Badge (overlaid, bottom-right)
│  │
│  ├─ MatchCardSpells
│  │  ├─ Summoner Spell 1 (e.g., Flash)
│  │  ├─ Summoner Spell 2 (e.g., Ignite)
│  │  ├─ Keystone Rune (e.g., Electrocute)
│  │  └─ Secondary Rune Tree Icon (e.g., Precision)
│  │
│  ├─ MatchCardStats
│  │  ├─ K/D/A Large Display ("8 / 9 / 7")
│  │  └─ KDA Ratio ("1.67:1 KDA")
│  │
│  ├─ MatchCardItems
│  │  ├─ Item Slot 0
│  │  ├─ Item Slot 1
│  │  ├─ Item Slot 2
│  │  ├─ Item Slot 3
│  │  ├─ Item Slot 4
│  │  ├─ Item Slot 5
│  │  └─ Trinket Slot (item6)
│  │
│  └─ MatchCardBadges
│     ├─ Multikill Badges (Double/Triple/Quadra/Penta)
│     ├─ Rank Badge (7th, 3rd, 1st, etc.)
│     └─ Performance Badge (Victor / Downfall)
│
└─ Right Column
   ├─ MatchCardTeams
   │  ├─ Allied Team List (5 players)
   │  │  └─ Each: Champion Icon + Summoner Name (bold if current user)
   │  │
   │  └─ Enemy Team List (5 players)
   │     └─ Each: Champion Icon + Summoner Name
   │
   └─ MatchCardAdvanced
      ├─ Laning Score ("Laning: 43 : 57")
      ├─ Kill Participation ("P/Kill: 60%")
      ├─ CS Score ("CS: 103 (5)")
      └─ Rank Badge ("Silver 2")
```

---

## Mobile Layout (Single Column, Stacked)

```
┌──────────────────────────────────────┐
│ MATCHCARD CONTAINER                  │
│ (Outcome-based background)           │
├──────────────────────────────────────┤
│                                      │
│  ┌────────────────────────────────┐  │
│  │ MatchCardHeader                │  │
│  │ Ranked Solo/Duo | 1 day ago    │  │
│  │ DEFEAT | 35m 44s               │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │     ┌────────┐                 │  │
│  │     │   🎮   │  Champion       │  │
│  │     │ [15]   │  + Level        │  │
│  │     └────────┘                 │  │
│  │                                │  │
│  │     ⚡ 🔥    🌲 ⚡            │  │
│  │   (Spells)  (Runes)           │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │     8  /  9  /  7              │  │
│  │   (Kills Deaths Assists)       │  │
│  │     1.67:1 KDA                 │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  📦 📦 📦 📦 📦 📦            │  │
│  │       👁️ (Trinket)            │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │ [Double Kill] [7th] [Downfall] │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │ Allied Team                    │  │
│  │ 🎮 Player 1                    │  │
│  │ 🎮 Player 2                    │  │
│  │ 🎮 damanjr (you)               │  │
│  │ 🎮 Player 4                    │  │
│  │ 🎮 Player 5                    │  │
│  │                                │  │
│  │ Enemy Team                     │  │
│  │ 🎮 Enemy 1                     │  │
│  │ 🎮 Enemy 2                     │  │
│  │ 🎮 Enemy 3                     │  │
│  │ 🎮 Enemy 4                     │  │
│  │ 🎮 Enemy 5                     │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │ Laning: 43 : 57                │  │
│  │ P/Kill: 60%                    │  │
│  │ CS: 103 (5)                    │  │
│  │ Rank: Silver 2                 │  │
│  └────────────────────────────────┘  │
│                                      │
└──────────────────────────────────────┘
```

---

## Color Palette

### Outcome Backgrounds

```css
.matchcard--defeat {
  background: linear-gradient(135deg, #4a2828 0%, #3a1818 100%);
  border-left: 4px solid #f87171;
}

.matchcard--remake {
  background: linear-gradient(135deg, #3a3a3a 0%, #2a2a2a 100%);
  border-left: 4px solid #6b7280;
}

.matchcard--victory {
  background: linear-gradient(135deg, #2c4a6e 0%, #1e3a5f 100%);
  border-left: 4px solid #60a5fa;
}
```

### Stat Colors

```css
.stat--kills {
  color: #4ade80;
} /* Green */
.stat--deaths {
  color: #f87171;
} /* Red */
.stat--assists {
  color: #60a5fa;
} /* Blue */
```

### Badge Colors

```css
.badge--multikill {
  background: #ef4444;
  color: white;
}

.badge--rank {
  background: #a78bfa;
  color: white;
}

.badge--victor {
  background: #3b82f6;
  color: white;
}

.badge--downfall {
  background: #f59e0b;
  color: white;
}
```

---

## Grid Structure (CSS Grid)

```css
.matchcard {
  display: grid;
  grid-template-columns: 200px 1fr 300px;
  gap: 16px;
  padding: 16px;
  border-radius: 8px;
}

.matchcard__left {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.matchcard__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.matchcard__right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Tablet breakpoint */
@media (max-width: 1024px) {
  .matchcard {
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
  }

  .matchcard__right {
    grid-column: 1 / -1;
  }
}

/* Mobile breakpoint */
@media (max-width: 640px) {
  .matchcard {
    grid-template-columns: 1fr;
  }
}
```

---

## Item Grid Structure

```css
.matchcard-items {
  display: grid;
  grid-template-columns: repeat(3, 48px);
  grid-template-rows: repeat(2, 48px) 48px;
  gap: 4px;
}

.matchcard-items__item {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.matchcard-items__item--empty {
  background: rgba(0, 0, 0, 0.5);
}

.matchcard-items__trinket {
  grid-column: 2;
  grid-row: 3;
}
```

---

## Team List Structure

```css
.matchcard-teams {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.matchcard-teams__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.matchcard-teams__player {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.matchcard-teams__player-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
}

.matchcard-teams__player-name {
  color: rgba(255, 255, 255, 0.8);
}

.matchcard-teams__player--current {
  font-weight: bold;
  color: rgba(255, 255, 255, 1);
}
```

---

## Badge Layout

```css
.matchcard-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

.matchcard-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
```

---

## Accessibility Notes

1. **Champion Portrait:**

   - Alt text: `{championName} level {champLevel}`
   - Example: "Ahri level 15"

2. **Items:**

   - Alt text: `{itemName}` or "Empty item slot"
   - Title attribute for hover tooltips

3. **Summoner Spells:**

   - Alt text: `{spellName}`
   - Example: "Flash", "Ignite"

4. **Runes:**

   - Alt text: `{runeName} (Keystone)` or `{treeNfame} (Secondary)`
   - Example: "Electrocute (Keystone)", "Precision (Secondary)"

5. **Team Players:**

   - Alt text on champion icons: `{championName}`
   - Aria-label on player rows: `{championName} played by {summonerName}`

6. **Badges:**
   - Screen reader text for context
   - Example: `<span aria-label="Achieved double kill">Double Kill</span>`

---

## Performance Considerations

### Image Loading Strategy

```typescript
// Lazy load images below the fold
<img
  loading="lazy"
  src={itemUrl}
  onError={handleImageError}
/>

// Preload critical images (champion portrait)
<link rel="preload" as="image" href={championUrl} />
```

### Component Memoization

```typescript
// Memo expensive components
const MatchCardTeams = React.memo(
  ({participants, currentPuuid}) => {
    // ...
  },
  (prev, next) => {
    return (
      prev.participants === next.participants &&
      prev.currentPuuid === next.currentPuuid
    );
  }
);
```

### Virtual Scrolling (if > 20 matches)

```typescript
import {Virtuoso} from "react-virtuoso";

<Virtuoso
  data={matches}
  itemContent={(index, match) => <MatchCard match={match} />}
/>;
```

---

## Animation Opportunities (Optional)

### Hover States

```css
.matchcard {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.matchcard:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
}
```

### Badge Entrance

```css
.matchcard-badge {
  animation: badge-pop-in 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

@keyframes badge-pop-in {
  0% {
    opacity: 0;
    transform: scale(0.5);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}
```

### Loading State

```css
.matchcard--loading {
  opacity: 0.6;
  pointer-events: none;
}

.matchcard--loading::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.1),
    transparent
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}
```

---

_This diagram complements MATCHCARD_UI_REDESIGN.md with visual layout reference_
