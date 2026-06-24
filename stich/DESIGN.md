---
name: Lumina TechNote
colors:
  surface: '#151218'
  surface-dim: '#151218'
  surface-bright: '#3c383f'
  surface-container-lowest: '#100d13'
  surface-container-low: '#1d1a21'
  surface-container: '#221e25'
  surface-container-high: '#2c292f'
  surface-container-highest: '#37333a'
  on-surface: '#e8e0e9'
  on-surface-variant: '#cdc3d3'
  inverse-surface: '#e8e0e9'
  inverse-on-surface: '#332f36'
  outline: '#968e9c'
  outline-variant: '#4b4451'
  surface-tint: '#d8b9ff'
  primary: '#d9baff'
  on-primary: '#421278'
  primary-container: '#c497ff'
  on-primary-container: '#532789'
  inverse-primary: '#7349aa'
  secondary: '#a5c8ff'
  on-secondary: '#00315e'
  secondary-container: '#0073d1'
  on-secondary-container: '#f7f8ff'
  tertiary: '#cdcd45'
  on-tertiary: '#323200'
  tertiary-container: '#b1b12a'
  on-tertiary-container: '#424200'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#eedcff'
  primary-fixed-dim: '#d8b9ff'
  on-primary-fixed: '#290054'
  on-primary-fixed-variant: '#5a2f90'
  secondary-fixed: '#d4e3ff'
  secondary-fixed-dim: '#a5c8ff'
  on-secondary-fixed: '#001c3a'
  on-secondary-fixed-variant: '#004785'
  tertiary-fixed: '#e9e95e'
  tertiary-fixed-dim: '#cccc44'
  on-tertiary-fixed: '#1d1d00'
  on-tertiary-fixed-variant: '#494900'
  background: '#151218'
  on-background: '#e8e0e9'
  surface-variant: '#37333a'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
  headline-md-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '500'
    lineHeight: '1.3'
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.0'
    letterSpacing: 0.05em
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  unit: 8px
  container-padding: 24px
  gutter: 16px
  sidebar-width: 280px
  max-content-width: 1200px
---

## Brand & Style

The design system is centered on a "High-Fidelity Industrial Assistant" aesthetic. It evokes a sense of advanced intelligence that is both powerful and unobtrusive. The brand personality is precise, calm, and visionary, moving away from generic AI tropes toward a refined, editorial technology experience.

The design style merges **Minimalism** with **Subtle Glassmorphism**. It utilizes expansive whitespace (or "dark-space"), ultra-thin translucent borders, and soft radial glows to indicate focus and system activity. Interactive elements favor a "Pill-shaped" geometry to feel approachable yet engineered. The emotional response should be one of quiet confidence and hyper-efficiency.

## Colors

The palette is bifurcated into high-clarity Dark and Light modes, with Dark being the expressive "Pro" default.

- **Dark Mode**: Uses a deep obsidian (#131314) for the canvas to allow high-contrast text and vibrant accents to pop. The sidebar and containers use a lifted charcoal (#1e1f20).
- **Light Mode**: Uses a soft, paper-white (#f8f9fa) with a cool-tinted grey (#f0f4f9) for secondary surfaces to maintain a clean, laboratory feel.
- **The Gradient**: A multi-stop "Gemini" inspired spectrum (Purple, Blue, Cyan, Magenta). This is used sparingly for primary actions, progress indicators, and AI-state signatures.
- **Borders**: All borders should be 0.5px to 1px wide using a translucent white (20% opacity) in dark mode or a translucent grey (10% opacity) in light mode.

## Typography

This design system uses a triple-font hierarchy to balance approachability with technical precision:

1.  **Headlines (Plus Jakarta Sans)**: Chosen for its modern, open apertures and professional yet friendly geometric curves. It provides the "Google Sans" spirit of clarity.
2.  **Body (Inter)**: The workhorse for high readability and UI utility. It scales perfectly from long-form notes to complex settings.
3.  **Utility/Labels (JetBrains Mono)**: Used for metadata, status tags, and technical labels to lean into the "Industrial Assistant" vibe.

Large display type should use tighter letter-spacing for a more editorial look, while small labels should use increased tracking for legibility.

## Layout & Spacing

The layout philosophy follows a **Fluid-Fixed Hybrid** model. The sidebar remains at a fixed 280px width (collapsible to a 72px icon rail), while the main content area occupies a fluid space with a maximum reading width of 1200px to ensure line-lengths for notes remain optimal.

- **Rhythm**: All spacing is derived from an 8px base unit.
- **Margins**: Mobile uses a 16px safe margin; Desktop uses a 24px-32px margin.
- **Breakpoints**: 
  - Mobile: < 600px (Sidebar becomes a bottom sheet or overlay)
  - Tablet: 600px - 1024px (Sidebar becomes a 72px icon rail by default)
  - Desktop: > 1024px (Full sidebar expanded)

## Elevation & Depth

This design system eschews traditional heavy shadows in favor of **Tonal Layering** and **Luminance**.

1.  **Base Layer**: The background (#131314).
2.  **Raised Layer**: Sidebar and cards (#1e1f20). Depth is communicated via a 1px `border-top` or `border-left` that is slightly lighter than the surface color to simulate a thin edge light.
3.  **Glass Layers**: Floating modals or tooltips use a backdrop blur (20px) with a semi-transparent surface.
4.  **Active State (The Glow)**: Focus states and active AI sections use a soft, large-radius radial gradient glow (e.g., a 150px blue/purple glow at 5% opacity) positioned behind the element rather than a drop shadow.

## Shapes

The shape language is strictly **Pill-shaped (3)** for interactive components. 

- **Primary Buttons & Inputs**: Full pill radius (999px).
- **Cards & Containers**: Large 1.5rem (24px) corners to contrast with the sharp 0.5px borders.
- **Icons**: Contained within circular or pill-shaped ghost backgrounds on hover.

The contrast between the "organic" rounded corners and the "industrial" thin lines creates a high-tech, polished feel.

## Components

- **Buttons**:
  - *Primary*: Pill-shaped. Uses the multi-color gradient background with white or high-contrast text.
  - *Ghost*: 1px translucent border, transparent background, becomes slightly more opaque on hover.
- **Input Fields**:
  - Minimalist pill-shaped containers. The border glows with a subtle 1px gradient stroke when focused. Background is a shade darker than the surface.
- **Chips**:
  - Small, mono-font labels inside pill-shaped strokes. Used for categorization or status.
- **Cards**:
  - Subtle 1px border. No shadows. Depth is achieved through a slight color shift (from #131314 to #1e1f20).
- **AI Insight Component**:
  - A specialized container featuring a thin "breathing" gradient border and a backdrop blur. This is the only component allowed to use the full accent gradient as a permanent visual element.
- **Lists**:
  - Spaced out with thin horizontal dividers. Hover states use a subtle "lift" effect where the background color lightens by 2%.