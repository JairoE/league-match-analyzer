# MatchCard Redesign - Documentation Index

## 📚 Complete Documentation Set

Based on screenshot analysis of target UI showing three match states (Defeat/Remake/Victory).

---

## 🎯 Start Here

### **MATCHCARD_REDESIGN_SUMMARY.md** ⭐

**Read this first**

High-level overview connecting all documents. Explains:

- The problem (TypeScript types incomplete)
- The solution (frontend refactor, not backend work)
- Key findings (90% of data already available)
- Quick start guide
- Success metrics

**Time to read:** 10 minutes  
**Audience:** Everyone (PMs, designers, developers)

---

## 📖 Core Documentation

### 1. **MATCHCARD_UI_REDESIGN.md**

**Detailed analysis of screenshot vs. current implementation**

Contains:

- Visual breakdown of all UI elements (15+ components)
- Three match states (Defeat/Remake/Victory) design
- Complete data availability matrix (what we have vs. what's missing)
- Type system updates needed
- Component restructuring strategy
- Styling requirements (colors, layout)
- Placeholder strategy for missing data
- Backend requirements assessment

**Time to read:** 20 minutes  
**Audience:** Developers, designers  
**Use when:** Understanding requirements, planning implementation

---

### 2. **RIOT_API_PARTICIPANT_FIELDS.md**

**Complete reference of 100+ Riot API fields**

Contains:

- Exhaustive field list with TypeScript types
- Categorized sections (champion, items, damage, vision, etc.)
- Priority fields for redesign (critical/important/nice-to-have)
- Data Dragon CDN URLs for all asset types
- Summoner spell ID → name mappings
- Rune style path mappings
- Implementation notes

**Time to read:** 30 minutes (reference, not meant to read front-to-back)  
**Audience:** Developers  
**Use when:** Updating TypeScript types, accessing Riot API data

---

### 3. **MATCHCARD_ACTION_PLAN.md**

**Step-by-step implementation guide**

Contains:

- 7 implementation phases with time estimates (15-22 hours total)
- Detailed file structure for modular components
- Props interfaces for each component
- Utility function signatures
- CSS requirements
- Achievement badge calculation logic
- Test cases and success criteria
- Risk mitigation strategies

**Time to read:** 25 minutes  
**Audience:** Developers  
**Use when:** Actually implementing the redesign

---

### 4. **MATCHCARD_LAYOUT_DIAGRAM.md**

**Visual layout reference**

Contains:

- ASCII art diagrams of desktop/mobile layouts
- Component hierarchy tree
- CSS Grid structure
- Color palette definitions
- Accessibility notes
- Performance considerations
- Animation opportunities

**Time to read:** 15 minutes  
**Audience:** Developers, designers  
**Use when:** Understanding layout, writing CSS

---

## 🗂️ Supporting Files

### **DECISIONS.md**

Lightweight ADR log with entry documenting this redesign analysis.

### **MATCHCARD_REDESIGN_INDEX.md** (you are here)

Navigation guide for all redesign documentation.

---

## 🚀 Quick Navigation by Role

### For Product Managers

1. Read: **MATCHCARD_REDESIGN_SUMMARY.md** (10 min)
2. Review: "Success Metrics" section
3. Check: "Estimated Total Effort" (15-22 hours)

### For Designers

1. Read: **MATCHCARD_REDESIGN_SUMMARY.md** (10 min)
2. Study: **MATCHCARD_LAYOUT_DIAGRAM.md** (15 min)
3. Review: Color palette and styling sections

### For Frontend Developers

1. Read: **MATCHCARD_REDESIGN_SUMMARY.md** (10 min)
2. Study: **MATCHCARD_UI_REDESIGN.md** (20 min)
3. Reference: **RIOT_API_PARTICIPANT_FIELDS.md** (as needed)
4. Follow: **MATCHCARD_ACTION_PLAN.md** (phase by phase)
5. Refer to: **MATCHCARD_LAYOUT_DIAGRAM.md** (while coding)

### For Backend Developers

1. Read: **MATCHCARD_REDESIGN_SUMMARY.md** (10 min)
2. Note: "Missing Data - Backend Requirements" section
3. Good news: Most work is frontend, minimal backend changes needed

---

## 📊 Documentation Quick Reference

| Document           | Pages | Primary Audience | When to Use                   |
| ------------------ | ----- | ---------------- | ----------------------------- |
| **Summary**        | 8     | Everyone         | First read, overview          |
| **UI Redesign**    | 12    | Devs, Designers  | Understanding requirements    |
| **API Fields**     | 10    | Devs             | Type definitions, data access |
| **Action Plan**    | 10    | Devs             | Step-by-step implementation   |
| **Layout Diagram** | 8     | Devs, Designers  | Visual reference, CSS         |

---

## 🔑 Key Findings (TL;DR)

### ✅ Good News

- 90% of data is already fetched from Riot API
- All items, spells, perks, champion level data available
- Backend is complete, no new API integrations needed
- Data stored correctly in database (`Match.game_info` JSONB)

### ⚠️ The Issue

- Frontend TypeScript types define only ~15 fields
- Riot API returns 100+ fields per participant
- Components can't access data because it's not typed

### 🎯 The Solution

- Update `Participant` type with 30+ new fields
- Create utility functions for calculations (KDA, kill participation, etc.)
- Restructure `MatchCard.tsx` into 10 modular components
- Apply new styling with outcome-based backgrounds
- Add placeholder images for missing assets

### 📈 Effort Estimate

- Core features: 15-22 hours
- With optional enhancements: 22-32 hours
- Complexity: Medium (frontend refactor, component restructuring)

---

## 🗺️ Implementation Phases

```
Phase 1: Type System (1-2h)
  └─ Update src/lib/types/match.ts

Phase 2: Utility Functions (2-3h)
  └─ Expand src/lib/match-utils.ts

Phase 3: Component Restructuring (4-6h)
  └─ Create src/components/MatchCard/ with 10 modules

Phase 4: Styling (3-4h)
  └─ Update MatchCard.module.css

Phase 5: Placeholder Assets (1h)
  └─ Create placeholder images

Phase 6: Achievement Badges (2-3h)
  └─ Implement badge calculation logic

Phase 7: Integration & Testing (2-3h)
  └─ Test all states, responsive layout, error handling
```

---

## 🎨 Design System

### Match States

- **DEFEAT**: Dark red (#4a2828), red border
- **REMAKE**: Gray (#3a3a3a), gray border
- **VICTORY**: Blue (#2c4a6e), blue border

### Stat Colors

- **Kills**: Green (#4ade80)
- **Deaths**: Red (#f87171)
- **Assists**: Blue (#60a5fa)

### Badge Colors

- **Multikill**: Red (#ef4444)
- **Rank**: Purple (#a78bfa)
- **Victor**: Blue (#3b82f6)
- **Downfall**: Orange (#f59e0b)

---

## 🧪 Testing Strategy

### Visual States

- [ ] Defeat card (red background)
- [ ] Remake card (gray background)
- [ ] Victory card (blue background)

### Data Display

- [ ] Champion level badge
- [ ] K/D/A with color coding
- [ ] 6 items + trinket
- [ ] Summoner spells
- [ ] Keystone + secondary rune
- [ ] Achievement badges
- [ ] All 10 players
- [ ] Current player highlighted

### Edge Cases

- [ ] Missing champLevel (show "missing")
- [ ] Empty item slots (show placeholder)
- [ ] Remake detection (short game + early surrender)
- [ ] Image load failures (fallback to placeholders)

### Responsive

- [ ] Desktop (3-column grid)
- [ ] Tablet (2-column grid)
- [ ] Mobile (single column stack)

---

## ❓ FAQ

### Q: Is this mostly backend or frontend work?

**A:** 95% frontend. Backend already fetches and stores all needed data.

### Q: Do we need new API endpoints?

**A:** No for core features. Optional: Timeline API (laning stats), Rank API (per-player ranks).

### Q: How long will this take?

**A:** 15-22 hours for core features. Can be split into phases.

### Q: Will this break existing functionality?

**A:** No. Old data is still accessible, just adding new fields and components.

### Q: What if some data is missing?

**A:** Display "missing" for text, use placeholders for images, skip badges if data unavailable.

### Q: Can we implement this in phases?

**A:** Yes. Suggested order: Types → Utils → Champion/Stats → Items/Spells → Teams → Badges.

### Q: What's the biggest risk?

**A:** Riot API response inconsistencies. Mitigate with optional chaining and null checks everywhere.

---

## 📝 Change Log

- **2026-02-04**: Initial documentation set created
  - Summary document
  - Detailed UI analysis
  - Complete API field reference
  - Step-by-step action plan
  - Visual layout diagrams
  - This index file
  - Entry added to DECISIONS.md

---

## 🔗 External References

### Riot API Documentation

- [Match-V5 API](https://developer.riotgames.com/apis#match-v5)
- [Data Dragon CDN](https://developer.riotgames.com/docs/lol#data-dragon)
- [Static Data](https://developer.riotgames.com/docs/lol#static-data)

### Current Implementation

- `league-web/src/components/MatchCard.tsx` (103 lines)
- `league-web/src/lib/types/match.ts` (59 lines)
- `league-web/src/lib/match-utils.ts` (existing utilities)

### Backend Services (Reference Only)

- `services/api/app/services/riot_sync.py` (match fetching)
- `services/api/app/services/riot_api_client.py` (Riot API client)

---

## 💡 Pro Tips

1. **Start with types** - Get TypeScript happy first, then build components
2. **Use optional chaining everywhere** - Riot API responses can be unpredictable
3. **Test with real data early** - Check network tab to see actual API responses
4. **Commit after each phase** - Easy rollback if something breaks
5. **Memo expensive components** - Rendering 10 players can be slow without optimization
6. **Use placeholder images** - Better UX than broken image icons
7. **Test all three states** - Defeat/Remake/Victory should look distinctly different

---

## 📧 Contact

For questions about:

- **Requirements & design**: See **MATCHCARD_UI_REDESIGN.md**
- **Data fields & types**: See **RIOT_API_PARTICIPANT_FIELDS.md**
- **Implementation steps**: See **MATCHCARD_ACTION_PLAN.md**
- **Layout & styling**: See **MATCHCARD_LAYOUT_DIAGRAM.md**
- **High-level overview**: See **MATCHCARD_REDESIGN_SUMMARY.md**

---

_Last updated: 2026-02-04_  
_Total documentation: ~50 pages across 5 files_  
_Estimated read time: 1-2 hours (full set)_
