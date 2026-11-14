# Mars Globe

Standalone interactive 3D Mars built on real NASA data (separate from the Rock Match backend). One file: `index.html`.

## Run

```bash
cd mars-globe
python3 -m http.server 8080
```

Open http://localhost:8080 (needs internet: NASA tiles stream live from Mars Trek).

## Features

- **Streams sharper NASA tiles as you zoom** (quadtree level-of-detail): from ~5 km/px for the whole planet down to ~325 m/px (Viking), ~165 m/px (HRSC relief) or ~80 m/px (THEMIS)
- **4 surface layers:** Viking color (optical), THEMIS day IR (thermal), MOLA color elevation (topographic), MOLA+HRSC shaded relief
- **Real 3D terrain** from the MOLA elevation model, with real relief lighting. Slider from flat to 10x; 1x = true scale
- **View angle** slider to tilt from top-down to looking across the horizon
- **Real sun position** for the current time on Mars (Mars24 algorithm): day/night terminator, season (Ls), time slider and play
- **Atmosphere** limb glow and haze, lit only on the day side
- **Phobos** (real NASA/ESA shape and imagery) and **Deimos** (generic shape), orbit radii to scale, moons enlarged 15x
- **Readouts:** lat/lon, elevation (m), local solar time, altitude, current imagery resolution
- **Measure tool:** great-circle distance plus elevation profile between two points
- Landing sites and ~36 named features, shown according to zoom level. Click to fly there

## Shareable views (URL parameters)

| Param | Example | Meaning |
|---|---|---|
| `lat`, `lon`, `alt` | `lat=-5.2&lon=137.6&alt=180` | camera position (alt in km) |
| `tilt` | `tilt=65` | view angle toward horizon (0–75°) |
| `layer` | `layer=themis` | `viking`, `themis`, `mola`, `hillshade` |
| `exag` | `exag=4` | terrain exaggeration |
| `sun` | `sun=lit` | always lit instead of real sun |
| `spin`, `atmo` | `spin=0&atmo=0` | turn off auto-rotate / atmosphere |

Examples:
- Gale Crater and Mount Sharp: `?lat=-5.2&lon=137.6&alt=180&sun=lit&exag=4`
- Valles Marineris flyover: `?lat=-16&lon=-72&alt=250&sun=lit&exag=4&tilt=68`

## Data and notes

- Tiles: NASA/JPL-Caltech Mars Trek WMTS (https://trek.nasa.gov)
- Elevation: 8-bit MOLA DEM, grey 0–255 = −8,201 to +21,241 m (≈115 m steps, smoothed). Checked against known elevations.
- Visible straight-line seams in the Viking layer (e.g. on Mount Sharp) are in NASA's original mosaic, not rendering bugs.
- Moon orbital phases are illustrative, not ephemeris positions.
