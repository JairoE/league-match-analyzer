Frontend Components Refactor Plan
Context
The league-web/src/components/ directory is a flat folder with 22 files (11 .tsx + 11 .module.css). The two largest files — MatchesTable.tsx (394 lines, 13 inline hooks, 3 eslint-disable suppressions) and MatchCard.tsx (535 lines, 3 internal sub-components) — have grown beyond comfortable single-file size. This refactor folderizes components, extracts hooks from MatchesTable, and decomposes MatchCard into separate files — all without changing behavior.

## Source of Truth for Participant Data

To prevent drift between Riot payload capabilities, frontend typing, and UI
rollout, use `docs/RIOT_API_PARTICIPANT_FIELDS.md` as the canonical source of
truth for participant fields and asset mappings.

Required alignment points:

- `league-web/src/lib/types/match.ts` (`Participant` typing coverage)
- `league-web/src/components/MatchCard.tsx` (field consumption in UI)
- `league-web/src/lib/constants/ddragon.ts` (spell/rune mapping parity)

When adding or changing MatchCard data usage, update this doc set together:

1. `docs/RIOT_API_PARTICIPANT_FIELDS.md` (field contract and priority)
2. `league-web/src/lib/types/match.ts` (typed contract)
3. `docs/MATCHCARD_REDESIGN.md` and `docs/app_state.md` (implementation status)

All core redesign steps (types, DDragon constants, match utilities, MatchCard UI, CSS) are fully implemented. This document tracks the remaining deferred features.

---

Phase — MatchCard Decomposition + CSS Var Extraction
Sub-component extraction
Move the 3 internal sub-components to their own files within MatchCard/:

ItemSlot.tsx (lines 66-83) — standalone, no shared state
Teams.tsx (lines 85-151) — already memo-wrapped, self-contained with TeamsProps
ChampionKdaChart.tsx (lines 153-229) — recharts chart, self-contained
Helper extraction
match-card.utils.ts — move pure functions out of the component body:

diffLabel() (line 345-348) — laning stat formatter
Multikill badge derivation (lines 301-313) — extract as getMultikillBadges(participant)
Outcome label/class resolution (lines 323-338) — extract as getOutcomeDisplay(outcome, styles)
Type extraction
types.ts — move MatchCardProps, TeamsProps, ChampionKdaChartProps, MultikillEntry here. Shared across the sub-component files.

CSS variable extraction (merged from original Phase 6)
In MatchCard.module.css, replace hardcoded hex colors with CSS custom properties defined in app/globals.css:

Current hardcoded value CSS variable
#1a2634 (victory bg) --match-victory-bg
#2d1a1a (defeat bg) --match-defeat-bg
#1e1e1e (remake bg) --match-remake-bg
#60a5fa (blue text) --match-text-blue
#f87171 (red text) --match-text-red
#6b7280 (gray text) --match-text-muted
#fbbf24 (gold badge) --badge-gold
Also update the inline hex values in ChampionKdaChart.tsx (bar fill colors: #60a5fa55, #f8717155, #6b728055) to use these variables with alpha.

Files changed
components/MatchCard/MatchCard.tsx — orchestrator only (~200 lines)
components/MatchCard/ItemSlot.tsx — new
components/MatchCard/Teams.tsx — new
components/MatchCard/ChampionKdaChart.tsx — new
components/MatchCard/match-card.utils.ts — new
components/MatchCard/types.ts — new
components/MatchCard/MatchCard.module.css — replace hardcoded hex with vars
components/MatchCard/index.ts — re-exports default
app/globals.css — add --match-_ and --badge-_ custom properties
Checkpoint: Visual comparison on /home and /riot-account/[riotId] pages — verify win/loss/remake colors, badge colors, chart bar colors, laning diff colors all render identically.

Verification
After all phases:

cd league-web && npm run lint — no new warnings
cd league-web && npm run build — clean build
Manual check: search for a summoner, verify match table renders, click rows to open detail panel, verify rank badges + lane stats + KDA chart + pagination all work
Confirm zero eslint-disable react-hooks/exhaustive-deps in MatchesTable/ directory
