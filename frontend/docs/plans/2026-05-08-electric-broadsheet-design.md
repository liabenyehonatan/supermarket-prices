# Electric Broadsheet — Design Spec
**Date:** 2026-05-08  
**Status:** Approved → Implementing

## Concept
"עיתון חשמלי" — Deep charcoal editorial base with electric lime accent. Feels like a luxury food magazine printed in a Tel Aviv print shop at midnight. Awwwards-level motion, asymmetric grid, typographic hierarchy as structure.

## Palette
| Token | Hex | Use |
|---|---|---|
| `ink-900` | `#0C0C12` | Deepest bg, overlays |
| `ink-800` | `#111118` | Body background |
| `ink-700` | `#1A1A24` | Card surfaces |
| `ink-600` | `#252535` | Elevated cards |
| `ink-500` | `#3A3A50` | Borders, dividers |
| `lime-400` | `#CCFF00` | Primary accent |
| `lime-300` | `#DEFF4D` | Lighter accent states |
| `editorial-white` | `#FAF9F6` | Primary text |
| `editorial-muted` | `#8A8A9A` | Secondary text |

## Typography
- **Display Hebrew:** Heebo Black 900 — structural headlines, chain names
- **Display Latin:** Bebas Neue — large numbers, English editorial labels
- **Body:** Assistant 400/600 — functional UI, body copy
- **Scale principle:** Extreme contrast — 96px display next to 11px labels, no middle ground

## Layout
- **Hero:** Asymmetric desktop grid `[1fr · 480px]` — left = editorial typographic zone, right = floating basket card
- **Results:** Editorial masonry ranking — #1 full-width banner, #2/#3 split row, #4+ compact list
- **Header:** Dark minimal + animated chain ticker below

## Motion
- **Load:** Staggered editorial reveal — masthead → tagline → stats → card (each 80ms offset)
- **Gradient mesh:** Slow 10s breathing animation behind hero
- **Hover:** Lime accent bloom + spring scale on store cards
- **Price counter:** Spring physics count-up (0 → final, with overshoot) on compare results
- **Ticker:** CSS infinite scroll of all 29 chain names

## Key Unique Elements
1. Animated ticker tape of chain names below header
2. Giant #1 store editorial banner — price rendered huge with count-up
3. Gradient mesh background (lime + violet nodes) that breathes
4. "₪" as oversized decorative watermark behind results
