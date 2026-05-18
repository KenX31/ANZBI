# UI Guideline

This document is the canonical UI guideline for the Wechat Pay ANZ Map project.

It is inspired by MongoDB's design system and adapted as the project's default visual direction for future frontend and browser-workspace work.

## 1. Visual Theme & Atmosphere

The target experience is deep-forest-meets-terminal: a design system rooted in the darkest teal-black (`#001e2b`) that evokes both the density of a data system and the depth of a forest canopy. Against this near-black canvas, a striking neon green (`#00ed64`) acts as the signature accent. It should feel electric and organic rather than synthetic.

The typography system uses three roles:

- `MongoDB Value Serif` for large hero headlines and editorial authority
- `Euclid Circular A` for body copy and UI text
- `Source Code Pro` for code, labels, and technical markers

The system should preserve a dual-mode structure:

- dark hero and feature sections on `#001e2b`
- light content sections on white with teal-gray borders

Key characteristics:

- deep teal-black backgrounds (`#001e2b`) instead of pure black
- neon green accent (`#00ed64`) used sparingly for impact
- serif display headings for hero moments only
- geometric sans-serif for navigation, body, and product UI
- wide-tracked monospace uppercase labels for technical voice
- teal-tinted shadows such as `rgba(0, 30, 43, 0.12)`
- pill buttons with green borders and rounded action surfaces
- cool-only palette: teal, green, blue, white, black

## 2. Color Palette & Roles

### Primary Brand

- Forest Black: `#001e2b`
- MongoDB Green: `#00ed64`
- Dark Green: `#00684a`

### Interactive

- Action Blue: `#006cfa`
- Hover Blue: `#3860be`
- Teal Active: `#1eaedb`

### Neutral Scale

- Deep Teal: `#1c2d38`
- Teal Gray: `#3d4f58`
- Dark Slate: `#21313c`
- Cool Gray: `#5c6c75`
- Silver Teal: `#b8c4c2`
- Light Input: `#e8edeb`
- Pure White: `#ffffff`
- Black: `#000000`

### Shadows

- Forest Shadow: `rgba(0, 30, 43, 0.12) 0px 26px 44px, rgba(0, 0, 0, 0.13) 0px 7px 13px`
- Standard Shadow: `rgba(0, 0, 0, 0.15) 0px 3px 20px`
- Subtle Shadow: `rgba(0, 0, 0, 0.1) 0px 2px 4px`

## 3. Typography Rules

### Font Families

- Display Serif: `MongoDB Value Serif`
- Body / UI: `Euclid Circular A`
- Code / Labels: `Source Code Pro`
- Fallbacks: `Akzidenz-Grotesk Std`, `Noto Sans KR`, `Noto Sans SC`, `Noto Sans JP`, `Times`, `Arial`, `system-ui`

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Hero | MongoDB Value Serif | 96px (6.00rem) | 400 | 1.20 | normal | Hero authority |
| Display Secondary | MongoDB Value Serif | 64px (4.00rem) | 400 | 1.00 | normal | Secondary hero |
| Section Heading | Euclid Circular A | 36px (2.25rem) | 500 | 1.33 | normal | Section titles |
| Sub-heading | Euclid Circular A | 24px (1.50rem) | 500 | 1.33 | normal | Feature titles |
| Body Large | Euclid Circular A | 20px (1.25rem) | 400 | 1.60 | normal | Introductory copy |
| Body | Euclid Circular A | 18px (1.13rem) | 400 | 1.33 | normal | Default body |
| Body Light | Euclid Circular A | 16px (1.00rem) | 300 | 1.50-2.00 | normal | Reading text |
| Nav / UI | Euclid Circular A | 16px (1.00rem) | 500 | 1.00-1.88 | 0.16px | Navigation and UI |
| Body Bold | Euclid Circular A | 15px (0.94rem) | 700 | 1.50 | normal | Strong emphasis |
| Button | Euclid Circular A | 13.5px-16px | 500-700 | 1.00 | 0.135px-0.9px | CTA text |
| Caption | Euclid Circular A | 14px (0.88rem) | 400 | 1.71 | normal | Metadata |
| Small | Euclid Circular A | 11px (0.69rem) | 600 | 1.82 | 0.2px | Tags and annotations |
| Code Heading | Source Code Pro | 40px (2.50rem) | 400 | 1.60 | normal | Code showcase |
| Code Body | Source Code Pro | 16px (1.00rem) | 400 | 1.50 | normal | Code blocks |
| Code Label | Source Code Pro | 14px (0.88rem) | 400-500 | 1.14 | 1px-2px | Uppercase technical labels |
| Code Micro | Source Code Pro | 9px (0.56rem) | 600 | 2.67 | 2.5px | Uppercase micro labels |

### Principles

- Use serif only for display-level hero moments.
- Favor weight `300` for comfortable body reading where supported.
- Use wide-tracked uppercase `Source Code Pro` labels to create a database-like technical tone.
- Keep hierarchy broad enough to distinguish editorial, product, and engineering layers.

## 4. Component Stylings

### Buttons

Primary green button on dark surfaces:

- background: `#00684a`
- text: `#000000`
- radius: `100px` or fully pill-shaped
- border: `1px solid #00684a`
- shadow: `rgba(0,0,0,0.06) 0px 1px 6px`
- hover: scale to `1.1`
- active: scale to `0.85`

Dark teal button:

- background: `#1c2d38`
- text: `#5c6c75`
- radius: `100px`
- border: `1px solid #3d4f58`
- hover background: `#1eaedb`
- hover text: `#ffffff`
- hover motion: `translateX(5px)`

Outlined button on light surfaces:

- background: transparent
- text: `#001e2b`
- border: `1px solid #b8c4c2`
- radius: `4px-8px`
- hover: light tinted background

### Cards & Containers

- Light cards: white background with `1px solid #b8c4c2`
- Dark cards: `#001e2b` or `#1c2d38` with `1px solid #3d4f58`
- Radius scale: `16px`, `24px`, `48px`
- Primary elevated shadow: `rgba(0,30,43,0.12) 0px 26px 44px`
- Image containers: `30px-32px` radius

### Inputs & Forms

- Text on dark inputs: `#e8edeb`
- Borders on light: `1px solid #b8c4c2`
- Borders on dark: `1px solid #3d4f58`
- Input radius: `4px`
- Textarea padding: `12px 12px 12px 8px`

### Navigation

- Dark header on `#001e2b`
- `Euclid Circular A`, `16px`, weight `500` for nav items
- CTA actions appear as pill buttons on the right
- Navigation should stay clean, deliberate, and product-oriented

### Distinctive Components

Neon accent underlines:

- use `#00ed64` or `#006cfa`
- visually expressed as bottom-border-led accents
- apply sparingly to feature headings and highlighted text

Source code label system:

- `Source Code Pro`
- `14px`
- uppercase
- `1px-2px` letter spacing
- use as small category markers above headings

## 5. Layout Principles

### Spacing System

- Base unit: `8px`
- Scale: `1px`, `4px`, `7px`, `8px`, `10px`, `12px`, `14px`, `15px`, `16px`, `18px`, `20px`, `24px`, `32px`

### Grid & Containers

- Keep content centered inside a max-width container.
- Use dark full-width hero and feature sections.
- Follow them with lighter content zones for density and contrast.
- Prefer `2-3` column card grids on larger screens.
- Keep footer full-width and visually anchored.

### Whitespace Philosophy

- Let dark sections breathe with generous vertical spacing.
- Keep light sections denser and more operational.
- Use mode transitions as part of the rhythm, not just spacing.

### Border Radius Scale

- Minimal: `1px-2px`
- Subtle: `4px`
- Standard: `8px`
- Card: `16px`
- Toggle: `20px`
- Large: `24px`
- Image: `30px-32px`
- Hero: `48px`
- Pill: `100px-999px`
- Full: `9999px`

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (Level 0) | No shadow | Default surfaces |
| Subtle (Level 1) | `rgba(0,0,0,0.1) 0px 2px 4px` | Light card lift |
| Standard (Level 2) | `rgba(0,0,0,0.15) 0px 3px 9px` | Standard cards |
| Prominent (Level 3) | `rgba(0,0,0,0.15) 0px 3px 20px` | Elevated panels |
| Forest (Level 4) | `rgba(0,30,43,0.12) 0px 26px 44px, rgba(0,0,0,0.13) 0px 7px 13px` | Hero cards |

The shadow system should stay teal-tinted where possible so depth remains inside the same color world as the brand.

## 7. Do's and Don'ts

### Do

- Use `#001e2b` for dark sections instead of pure black.
- Use `#00ed64` sparingly so it keeps its electric impact.
- Reserve `MongoDB Value Serif` for hero and display contexts only.
- Use `Source Code Pro` uppercase with wide tracking for technical labels.
- Use teal-tinted shadows for major elevation.
- Preserve clear dark and light section boundaries.
- Prefer body weight `300` where readability remains strong.
- Apply pill radius to primary CTAs.

### Don't

- Do not use pure black for dark section backgrounds.
- Do not flood layouts with `#00ed64`; keep it as an accent.
- Do not use neutral gray shadows when a teal-tinted shadow is available.
- Do not use serif for body text.
- Do not tighten tracking on label-style monospace text.
- Do not mix dark and light treatments inside the same visual section without a deliberate transition.
- Do not introduce warm accent colors.

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile Small | <425px | Tight single-column layout |
| Mobile | 425-768px | Standard mobile layout |
| Tablet | 768-1024px | Two-column grids begin |
| Desktop | 1024-1280px | Standard desktop layout |
| Large Desktop | 1280-1440px | Expanded layout |
| Ultra-wide | >1440px | Max-width with generous margins |

### Responsive Rules

- Scale hero type down progressively from `96px`.
- Collapse navigation into a compact menu on smaller widths.
- Stack feature cards vertically on mobile.
- Maintain dark/light section identity at all breakpoints.
- Preserve image radius and visual rhythm consistently.

## 9. Agent Prompt Guide

### Quick Color Reference

- Dark background: `#001e2b`
- Brand accent: `#00ed64`
- Functional green: `#00684a`
- Link blue: `#006cfa`
- Text on light: `#000000`
- Text on dark: `#ffffff` or `#e8edeb`
- Border light: `#b8c4c2`
- Border dark: `#3d4f58`

### Example Prompts

- Create a hero on `#001e2b` with a large serif headline, one neon green highlight, and a pill CTA using `#00684a`.
- Design a light-mode card with a `#b8c4c2` border, `16px` radius, and a forest-tinted shadow.
- Build a dark feature section with white copy, dark cards, and green underline accents.
- Create a technical label in `Source Code Pro`, uppercase, with `2px` letter spacing.
- Design a pill button using `#1c2d38`, `#3d4f58`, and hover state `#1eaedb`.

### Iteration Guide

1. Start by choosing section mode: dark hero/feature or light content.
2. Use `#00ed64` once per section unless a stronger product reason exists.
3. Keep serif usage limited to display text.
4. Prefer lighter body weights for calm reading density.
5. Use wide-tracked code labels to preserve the technical identity.
6. Keep shadows and borders aligned with the teal-based palette.

## 10. Project Usage Rule

For this repository, this document should be treated as the default UI guideline for:

- browser workspace styling
- future frontend component design
- mockups and prototypes
- prompt guidance for AI-assisted UI generation

If an implementation must diverge, document the reason in the relevant task or PR so the design language stays intentional rather than drifting.
