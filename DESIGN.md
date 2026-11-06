# Design System — applied subset

Authority: the user's Agent Evolution — Design System v0.1. This is an Operate surface for desktop evidence inspection. The existing visual system is fixed, not redesigned.

Colors: background #F5F6F8; surface #FFFFFF; secondary #EEF1F5; text #202B3C; secondary text #64748B; border #E2E6ED; primary #3867D6; success #16865B; warning #C88724; danger #D64B4B; information #477AC7. Use text labels alongside color; darken semantic foregrounds if needed for text contrast.

Typography: Geist Sans (locally served) with Chinese system fallbacks; JetBrains Mono for identifiers and JSON. Titles 26px, section titles 17px, body 14px, secondary 12px. Numeric columns use tabular numerals.

Layout: 232px left navigation, 56px context bar, 28px content padding; target desktop 1440px. Tables and divided sections take priority over dashboard cards. 4px spacing grid. Bordered panels use 8px radius. No decorative gradients or animations. Shadows only for floating surfaces.

Evidence: sample counts always have denominators; unknown values use an em dash with an explanation. Execution status and evaluation verdict are distinct. Trace row selection updates evidence details. Score evidence links select their source node. Explicit, persistent preview banner in all fixture views. Default workspace contains no fabricated results.

Responsive behavior: at narrow sizes collapse navigation to labeled horizontal links, stack evidence panels, constrain table overflow to its own scroll container. Visible keyboard focus, form labels, semantic tables, status text and error recovery are required.
