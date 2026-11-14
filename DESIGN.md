# Mars Excursion Planner — Design System Reference

**NASA Space Apps Challenge** | Design Lead: [Your Name]

---

## File Structure

```
styles/
├── tokens.css       # CSS custom properties (colors, type, spacing, etc.)
├── layout.css       # App shell layout (header, rail, map, panel, strip)
└── components.css   # Reusable UI components
design-preview.html  # Live component showcase
```

Import order in HTML:
```html
<link rel="stylesheet" href="styles/tokens.css">
<link rel="stylesheet" href="styles/components.css">
<link rel="stylesheet" href="styles/layout.css">  /* optional, for app shell */
```

---

## Design Tokens (tokens.css)

### Colors

#### Base
| Token | Value | Use |
|-------|-------|-----|
| `--color-bg` | `#0B0D10` | Page background |
| `--color-bg-elevated` | `#101317` | Cards, overlays |
| `--color-panel` | `#14181D` | Panels, rails, header |
| `--color-panel-hover` | `#1A1F26` | Hover states |
| `--color-border` | `#2A313A` | Default borders |
| `--color-border-strong` | `#3A424D` | Emphasized borders |
| `--color-border-subtle` | `#222830` | Dividers |

#### Text
| Token | Value | Use |
|-------|-------|-----|
| `--color-text-primary` | `#E8ECEF` | Primary text |
| `--color-text-secondary` | `#9AA4B2` | Secondary text |
| `--color-text-muted` | `#6B7583` | Labels, disabled |
| `--color-text-inverse` | `#0B0D10` | On accent |
| `--color-text-disabled` | `#4A5360` | Disabled text |

#### Accent
| Token | Value | Use |
|-------|-------|-----|
| `--color-accent` | `#E8743B` | Primary actions, focus |
| `--color-accent-hover` | `#D66830` | Hover |
| `--color-accent-active` | `#C45D28` | Active/pressed |
| `--color-accent-muted` | `rgba(232,116,59,0.12)` | Backgrounds |
| `--color-accent-glow` | `rgba(232,116,59,0.25)` | Focus rings |

#### Rock Types (Colorblind-Safe — distinct hues + shapes)
| Token | Value | Shape | Use |
|-------|-------|-------|-----|
| `--color-clay` | `#2BB3A3` | Circle | Clay-bearing (phyllosilicates) |
| `--color-sulfate` | `#F2B134` | Triangle | Sulfate-rich (evaporites) |
| `--color-silica` | `#9B7FE8` | Diamond | Silica-rich (opaline) |

*Each has `-muted` (12% opacity) and `-border` (35% opacity) variants.*

#### Status (Semantic)
| Token | Value | Use |
|-------|-------|-----|
| `--color-go` | `#2BB3A3` | Safe, complete, nominal |
| `--color-caution` | `#F2B134` | Warning, attention needed |
| `--color-hazard` | `#E5484D` | **Danger only** — reserved |

*Each has `-muted` and `-border` variants.*

#### Confidence Badges
| Token | Value | Use |
|-------|-------|-----|
| `--color-measured` | `#2BB3A3` | Direct detection (solid border) |
| `--color-estimated` | `#F2B134` | Inferred (dashed border) |

### Typography

| Token | Value |
|-------|-------|
| `--font-ui` | `Inter` (fallback: system UI) |
| `--font-mono` | `JetBrains Mono` (fallback: `Fira Mono`, `SF Mono`, `Menlo`) |
| `--font-label` | `var(--font-ui)` |

| Size | Token | px |
|------|-------|-----|
| XS | `--text-xs` | 10px |
| SM | `--text-sm` | 12px |
| Base | `--text-base` | 14px |
| LG | `--text-lg` | 16px |
| XL | `--text-xl` | 18px |
| 2XL | `--text-2xl` | 24px |

Weights: `--font-weight-normal` (400), `--font-weight-medium` (500), `--font-weight-semibold` (600), `--font-weight-bold` (700)

### Spacing (4px base)
`--space-1` (4px) through `--space-16` (64px)

### Border Radius
`--radius-none` (0), `--radius-sm` (2px), `--radius-md` (4px), `--radius-lg` (6px), `--radius-xl` (8px), `--radius-full` (9999px)

### Layout Constants
| Token | Value |
|-------|-------|
| `--header-height` | 48px |
| `--rail-width` | 280px |
| `--panel-width` | 320px |
| `--strip-height` | 120px |
| `--touch-target-min` | 44px |

---

## Layout (layout.css)

### App Shell Grid
```css
.planner-app {
  grid-template-areas:
    "header header header"
    "rail   map    panel"
    "strip  strip  strip";
  grid-template-rows: var(--header-height) 1fr var(--strip-height);
  grid-template-columns: var(--rail-width) 1fr var(--panel-width);
}
```

### Areas
| Area | Class | Description |
|------|-------|-------------|
| Header | `.planner-header` | Top bar: title, actions |
| Rail | `.planner-rail` | Left: layer toggles, rock filters |
| Map | `.planner-map` | Center: WebGL/Canvas map (~70%) |
| Panel | `.planner-panel` | Right: route stats, safety |
| Strip | `.planner-strip` | Bottom: sample progress + elevation |

### Responsive Breakpoints
- **Desktop** (>1024px): Full 5-area grid
- **Tablet** (≤1024px): Narrower rail/panel
- **Mobile** (≤768px): Stacked — header → rail → map → panel → strip
- **Narrow** (≤480px): Compressed padding, smaller header

---

## Components (components.css)

### Buttons
| Class | Description |
|-------|-------------|
| `.btn` | Base |
| `.btn-primary` | Mars accent, primary actions |
| `.btn-secondary` | Panel bg, secondary actions |
| `.btn-ghost` | Minimal, toolbar actions |
| `.btn-danger` | Hazard red — **danger only** |
| `.btn-sm` / `.btn-lg` | Size variants |
| `.btn-icon` | Icon-only (44×44 min) |
| `.btn:disabled` | Disabled state |

### Toggle Switch (Layer Controls)
```html
<label class="toggle">
  <input type="checkbox" checked>
  <span class="toggle-track"></span>
  <span class="toggle-label">Layer Name<span class="toggle-subtitle">Subtitle</span></span>
</label>
```

### Rock Type Markers (Distinct Shapes)
| Class | Shape | Color |
|-------|-------|-------|
| `.marker-clay` | Circle | Teal `#2BB3A3` |
| `.marker-sulfate` | Triangle | Amber `#F2B134` |
| `.marker-silica` | Diamond | Violet `#9B7FE8` |

Sizes: `.marker-sm`, `.marker` (default), `.marker-lg`

### Confidence Badges
| Class | Style |
|-------|-------|
| `.badge-measured` | Solid border, teal text |
| `.badge-estimated` | **Dashed border**, amber text |

### Status Chips
| Class | Use |
|-------|-----|
| `.chip-go` | Safe/nominal |
| `.chip-caution` | Warning |
| `.chip-stop` | **Danger only** |

All include `.chip-dot` indicator.

### Route Stat Card
```html
<div class="stat-card">
  <span class="stat-card-label">Label</span>
  <div class="stat-card-value">12.4<span class="stat-card-unit">km</span></div>
  <div class="stat-card-detail">
    <span>Detail text</span>
    <span class="stat-card-trend positive">+0.6</span>
  </div>
</div>
```

Trends: `.positive` (go), `.negative` (hazard), `.neutral` (caution)

### Site Card
```html
<article class="site-card">
  <header class="site-card-header">
    <h3 class="site-card-title">Site Name</h3>
    <div class="site-card-rock"><span class="marker marker-clay"></span><span>Clay</span></div>
  </header>
  <div class="site-card-meta">
    <div class="site-card-meta-item">
      <span class="site-card-meta-label">Elevation</span>
      <span class="site-card-meta-value">-4,212 m</span>
    </div>
    ...
  </div>
  <div class="site-card-actions">
    <button class="btn btn-primary btn-sm">Add to Route</button>
    <button class="btn btn-secondary btn-sm">Details</button>
  </div>
</article>
```

### Legend
```html
<div class="legend">
  <div class="legend-group">
    <span class="legend-group-title">Group Title</span>
    <div class="legend-item"><span class="marker marker-clay"></span>Label</div>
  </div>
</div>
```

### Layer Toggle Item (Rail)
```html
<div class="layer-item">
  <div class="layer-item-info">
    <span class="layer-item-name">Layer Name</span>
    <span class="layer-item-type">Type • Detail</span>
  </div>
  <label class="layer-item-toggle toggle">...</label>
</div>
```

### Rock Filter Item (Rail)
```html
<label class="rock-filter-item">
  <input type="checkbox" checked>
  <span class="rock-filter-swatch rock-filter-swatch-clay"></span>
  <span class="rock-filter-name">Clay-bearing</span>
</label>
```

Swatches: `.rock-filter-swatch-clay`, `.rock-filter-swatch-sulfate`, `.rock-filter-swatch-silica`

### Loading State
```html
<div class="loading">
  <div class="loading-spinner"></div>
  <span class="loading-text">Loading…</span>
</div>
```

### Empty State
```html
<div class="empty-state">
  <svg class="empty-state-icon" ...></svg>
  <h3 class="empty-state-title">Title</h3>
  <p class="empty-state-text">Description</p>
  <button class="btn btn-primary empty-state-action">Action</button>
</div>
```

### Elevation Profile (Strip)
```html
<div class="elevation-profile">
  <canvas class="elevation-canvas"></canvas>
  <div class="elevation-stats">
    <div class="elevation-stat"><span class="elevation-stat-label">Min:</span><span class="elevation-stat-value">-4,521 m</span></div>
    ...
  </div>
</div>
```

### Sample Progress (Strip)
```html
<div class="sample-progress">
  <div class="sample-progress-list">
    <div class="sample-item completed">
      <span class="sample-number">1</span>
      <div class="sample-info">
        <div class="sample-name">Site Name</div>
        <div class="sample-type">Clay • Measured</div>
      </div>
      <span class="chip chip-go">Complete</span>
    </div>
    <div class="sample-item current">...</div>
    <div class="sample-item">...</div>
  </div>
</div>
```

States: `.completed`, `.current`, default (pending)

---

## Usage Guidelines

### Do
- Use semantic status colors (go/caution/hazard) — not raw rock colors for status
- Use mono font (`var(--font-mono)`) for all numbers, coordinates, bearings
- Use uppercase labels (`var(--font-label)`, `--text-xs`, letter-spacing) for UI chrome
- Keep borders 1px (`var(--color-border)`)
- Maintain 44px minimum touch targets
- Use distinct marker shapes — never rely on color alone

### Don't
- Use `--color-hazard` for anything but immediate danger
- Use heavy gradients or shadows
- Mix rock colors with status meanings (clay teal ≠ GO)
- Use estimated (dashed) badge for measured data
- Drop below 44px touch targets

---

## Browser Support
Modern evergreen browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+). CSS custom properties required.

---

## Fonts
Load via Google Fonts in HTML `<head>`:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## Team Handoff
- **Data/Globe team**: Consumes rock type colors/shapes from tokens, emits GeoJSON with `rockType` + `confidence` properties
- **Routing team**: Reads route stats format, emits elevation profile data for canvas
- **All**: Import `tokens.css` for shared values; `components.css` for UI; `layout.css` only for app shell