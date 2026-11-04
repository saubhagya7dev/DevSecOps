# Sunrise reference study — 2026-11-04

Reference: https://pro.reactbits.dev/docs/blocks/features/features-17?variantSort=latest

Evidence: live preview inspected in its default center state, then Sydney and New York states; user supplied full-size screenshots of all three positions. The public preview uses a full-section canvas. This study describes visible behavior, not the vendor's paid implementation.

## What makes it look like sunrise

- A near-black sky is populated with many tiny, irregularly spaced stars. Their brightness and hue vary subtly; they are texture, not large glowing particles. The stars extend behind the heading and roles.
- The planet is a dark filled hemisphere occupying the bottom of the scene. The top of the silhouette is a broad shallow curve, highest in the center and lower at either side. A line by itself does not create this depth.
- A thin, sharp luminous atmospheric rim separates the planet from the sky. There is a cool blue/violet atmosphere around the unlit side, while the sunlit segment turns coral, peach, and pale white.
- The brightest white-peach crest sits ON the curved horizon. It is not a floating circular sun or an elliptical spot pasted onto a constant-height line.
- Several scales of light surround the crest: a concentrated white core; peach/coral near-field bloom; rose/violet middle atmosphere; broad navy/blue outer falloff. Warm light also spills faintly onto the otherwise dark planet.
- The light rises into the sky and spreads along the rim. Its vertical extent and horizontal extent differ, producing a sunrise rather than a round radial glow.
- Hovering a role moves the crest and all warm scattering together. The vertical position follows the planet curve. The far side stays cool. The planet silhouette stays fixed.
- Active text becomes white and its small label warm orange; inactive labels and descriptions are dimmer. Role regions remain unboxed.

## Why the previous implementation missed it

The old scene was only 85px tall, contained no stars, and used a CSS border ellipse with a fixed-height blurred gradient. There was no filled planetary silhouette, multiscale atmospheric scattering, or curved path for the moving sun. The effect occupied a strip below the roles rather than forming the scene behind them.

## Rebuild plan

Use an original local canvas renderer across the full introduction: deterministic fine star texture, a filled dark hemisphere, layered cool atmosphere, warm multiscale sunrise scattering, and a crisp color-varying rim. Derive the sun's height from the same curve used to draw the planet. Animate only while transitioning between role positions, pause when hidden/offscreen, and snap to the selected state under reduced motion. Preserve sharp UI borders, the separate edge-light effect, and the existing Obsidian repository graph.

## Implemented comparison

Commit `cf92c6a` replaces the earlier CSS strip with an original Canvas 2D renderer across the whole introduction. No external imagery, paid source code, packages, or CDN requests were added.

The renderer caches a deterministic star texture at the measured canvas size, draws broad cool atmosphere and several warm scattering scales, fills the planetary silhouette in front of the light, and finishes with a thin gradient rim and flattened white-peach crest. The crest height is calculated from the same quadratic as the planet, so moving left/right lowers it naturally. A faint amber reflection is clipped to the planet below the sunrise.

The transition uses elapsed frame time rather than a refresh-rate-dependent step. It stops once settled; hidden/offscreen scenes do not keep drawing. Reduced motion snaps to the chosen role. Role text changes color, with no role borders or boxes. The existing whole-UI border illumination and graph implementation are unchanged.

Validation:

- Inspected the actual local center, Analyst, and Reviewer states in the browser and compared them with the reference's center/left/right states. Confirmed warm scattering moves with the crest and the opposite atmosphere remains cool.
- Removed a visible purple stroke band during visual refinement so the outer atmosphere is diffuse.
- Checked a 390 × 844 viewport: the introduction and roles fit without horizontal document overflow (375px content width plus the viewport scrollbar).
- `node --check web/app.js`: passed.
- `node --test tests/test_sunrise.cjs tests/test_edge_light.cjs tests/test_graph.cjs tests/test_markdown.cjs`: 30 passed.
- New tests verify curve/planet agreement, deterministic bounded star generation, transition settling, reduced motion, and offscreen redraw suspension.
- `git diff --check`: passed.

This is a reference-informed recreation of the visual behavior, not a claim of a pixel-identical copy. The earlier generated concept images and 85px CSS-strip descriptions in the initial landing update are superseded by this implementation.
