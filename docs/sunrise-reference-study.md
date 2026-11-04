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
