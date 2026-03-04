Frontend Components Refactor Plan
Context
The league-web/src/components/ directory is a flat folder with 22 files (11 .tsx + 11 .module.css). The two largest files — MatchesTable.tsx (394 lines, 13 inline hooks, 3 eslint-disable suppressions) and MatchCard.tsx (535 lines, 3 internal sub-components) — have grown beyond comfortable single-file size. This refactor folderizes components, extracts hooks from MatchesTable, and decomposes MatchCard into separate files — all without changing behavior.

Phase 1 — Folderize (zero logic changes)
Move each component into its own folder with its CSS module. No barrel files for single-export folders — import the component file directly.

Target structure after Phase 1

components/
Auth/
AuthForm.tsx
AuthForm.module.css
SignInForm.tsx
SignUpForm.tsx
Header/
Header.tsx
Header.module.css
SearchBar/
SearchBar.tsx
SearchBar.module.css
SubHeader/
SubHeader.tsx
SubHeader.module.css
Pagination/
Pagination.tsx
Pagination.module.css
MatchRow/
MatchRow.tsx
MatchRow.module.css
MatchDetailPanel/
MatchDetailPanel.tsx
MatchDetailPanel.module.css
MatchCard/
MatchCard.tsx
MatchCard.module.css
index.ts ← barrel (will have 3+ exports after Phase 3)
MatchesTable/
MatchesTable.tsx
MatchesTable.module.css
index.ts ← barrel (will have 3+ exports after Phase 2)
FeatureCard/
FeatureCard.tsx
FeatureCard.module.css
Import updates required
Page files (4 files):

app/page.tsx — Header, SearchBar, FeatureCard (3 imports)
app/home/page.tsx — Header, SubHeader, SearchBar, MatchesTable (4 imports)
app/auth/page.tsx — Header, SignInForm, SignUpForm (3 imports)
app/riot-account/[riotId]/page.tsx — Header, SubHeader, SearchBar, MatchesTable (4 imports)
Cross-component imports (3):

MatchesTable.tsx imports MatchRow, MatchDetailPanel, Pagination
MatchDetailPanel.tsx imports MatchCard
SignInForm.tsx and SignUpForm.tsx import AuthForm
Execution order
Move leaf components first (no cross-component imports): Header, SearchBar, SubHeader, Pagination, FeatureCard
Move Auth/ group: AuthForm + SignInForm + SignUpForm together
Move MatchRow
Move MatchCard (+ add index.ts)
Move MatchDetailPanel
Move MatchesTable (+ add index.ts)
Trivial fixes to include during Phase 1:

Add type="button" to any non-submit <button> elements encountered during moves
Checkpoint: npm run lint && npm run build after every 2-3 moves.

Phase 2 — MatchesTable Hook Extraction
Extract 2 custom hooks from MatchesTable.tsx. Keep championHistoryByMatchId useMemo inline (it's a pure derivation, not worth a separate file).

Hook 1: useMatchSelection.ts
Location: components/MatchesTable/useMatchSelection.ts

Extracts:

selectedMatchId state + setSelectedMatchId
handleRowClick callback (toggle logic)
handleClosePanel callback
Returns: { selectedMatchId, handleRowClick, handleClosePanel, clearSelection }

clearSelection replaces the inline setSelectedMatchId(null) calls in tab click handlers
Why separate: Selection is a distinct UI concern from data fetching.

Hook 2: useMatchDetailData.ts
Location: components/MatchesTable/useMatchDetailData.ts

Extracts all 3 fetch-on-select effects + their state:

championById state + champion loading effect (lines 124-158)
rankByPuuid state + rank batch fetch effect (lines 160-184)
laneStatsByMatchId state + timeline stats fetch effect (lines 186-215)
Parameters:

type UseMatchDetailDataParams = {
selectedMatchId: string | null;
matches: MatchSummary[];
matchDetails: Record<string, MatchDetail>;
getParticipantForMatch: (match: MatchSummary) => Participant | null;
championIdsToLoad: number[];
};
Returns: { championById, rankByPuuid, laneStatsByMatchId }

Why combined: All three follow the identical pattern (fetch on selection change, cache in a map). Grouping avoids 3 near-identical files.

ESLint fix: Stabilize deps properly in each effect to remove all 3 eslint-disable-next-line react-hooks/exhaustive-deps comments:

Champion effect: dep on championIdsToLoad is correct; the championById read inside uses functional updater setChampionById(prev => ...) so it doesn't need to be a dep — this is already correct, the eslint-disable can be removed if championIdsToLoad is the only dep and the filter uses prev inside the setter instead of the outer closure
Rank effect: add rankByPuuid to deps or use functional updater pattern to avoid stale closure
Timeline effect: similar — use functional updater for laneStatsByMatchId
Additional extractions
constants.ts — move COLUMNS array out of MatchesTable.tsx
SkeletonRows.tsx — move the SkeletonRows component (lines 48-65) to its own file

Files changed
components/MatchesTable/MatchesTable.tsx — slimmed down, imports hooks
components/MatchesTable/useMatchSelection.ts — new
components/MatchesTable/useMatchDetailData.ts — new
components/MatchesTable/constants.ts — new (COLUMNS)
components/MatchesTable/SkeletonRows.tsx — new
components/MatchesTable/index.ts — re-exports default
Checkpoint: Verify all 6 behaviors:

Tab switching clears selection
Row click toggles detail panel
Panel close button works
Rank badges appear in Teams
Lane stats (CS@10, CS@15, G@10) appear
Pagination controls work
Phase 3 — MatchCard Decomposition + CSS Var Extraction
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
