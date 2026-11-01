# Investigation workbench

The interface implements the approved black, square-edged design with compact typography, thin straight graph connectors, and softly glowing multicolored nodes. A device-pixel-ratio-aware Canvas 2D renderer now runs the graph locally with spring forces, inverse-square repulsion, center gravity, and velocity damping. It uses the existing HTML, CSS, JavaScript, and same-origin Python API. No React runtime, external font request, or additional package is required.

## Repository graph

- File nodes come from the pinned repository tree and inspected file artifacts. Preparation events reveal successfully read files before the repository artifact is saved.
- Solid lines represent folder membership or grouping of observed technologies. They are not imports, runtime calls, network reachability, or a claim of architectural completeness.
- Evidence mode adds observation and original-report nodes. Dashed lines represent cited associations. A source is connected to repository observations only when an accepted finding references both; retrieval alone does not establish relevance.
- Architecture colors distinguish repository groups. The optional CVSS heatmap colors advisory nodes by their published score; it does not propagate those scores to associated files or claim target exploitability. Uninspected files are dimmed; the selected node has an independent outline.
- Inspected files take priority within a 160-file view. Additional observations and technology/source nodes are bounded separately. Omitted tree entries are counted. Full saved artifacts remain available in the Evidence tab and JSON export.
- Search highlights matches; the inspected-only filter removes uninspected file nodes. Select a node to open its inspector. Drag the background to pan, drag a node to tug its connected neighbors, wheel to zoom around the cursor, or pinch with two touch pointers. HUD +, −, and Fit buttons remain available. Canvas keyboard controls are arrows to pan, +/− to zoom, and 0 to fit. The expandable text node list provides keyboard selection. Hover spotlights direct connections and related reviewer evidence chains while dimming unrelated nodes.

## Graph controls and CVSS provenance

The floating control panel provides keyboard-accessible Groups, Filters, Colors, Display, and Forces tabs:

| Tab | Controls |
| --- | --- |
| Groups | Critical, High, Medium, Low, Clean/CVSS 0, and Unscored checkboxes |
| Filters | Keyword search over names, paths, groups and CVE identifiers; orphans; minimum CVSS |
| Colors | Repository groups, cited service/component layers, or published-CVSS heatmap |
| Display | Node scale, link thickness, hover/large/all labels, candidate attack-path pulses |
| Forces | Center gravity, repulsion charge, link distance, velocity damping, reset |

Service/component-layer coloring uses the analyst component names and their verified observation IDs; nodes without a cited component remain Unmapped. This is a source-based map, not verified deployment topology. Keyword search also covers these component names.

A positive minimum CVSS excludes nodes without numeric scores. Scores belong to advisory nodes; repository files are not declared vulnerable merely because a package name matches. Clean means an explicitly published score of zero, never missing data. Older artifacts remain Unscored when no numeric score was retained.

GitHub's published `cvss_severities` values are retained with score version, vector, provider and advisory ID. Version 4 is preferred where supplied; version 3 is otherwise used. Both ratings survive alias merging. Out-of-range, nonnumeric, boolean, infinite and NaN values are rejected. OSV vector strings and qualitative severity labels are not converted into guessed numeric scores. See [GitHub's global-advisory schema](https://docs.github.com/en/rest/security-advisories/global-advisories). Restart the backend and start a new analysis to collect this metadata; existing saved artifacts are not rewritten.

Path particles animate only reviewer finding/citation links in evidence mode. They depict candidate evidence associations, not confirmed exploit paths. They never run exploits. Architecture/grouping edges and advisory package associations cannot create a verified attack path. Hovering traces related citations without adding new claims.

The simulation reheats after manipulation and settles to rest. Empty/fully filtered graphs do not keep a hot simulation loop. Off-screen or hidden documents pause animation. Once you pan, zoom or grab a node, automatic framing stops so it cannot fight your gesture. Fit restores framing. Reduced-motion preference disables particle pulses.

![Canvas graph and force controls](assets/graph-controls.png)

## Inspector and live progress

The desktop workspace pairs a square graph on the left with Live Investigation above Evidence Inspector on the right. On narrow screens these panels stack, and the graph keeps its square aspect ratio. The opening explanation describes the product before asking for a repository URL.

Five clickable stages show snapshot preparation, Repository Analyst, Incident Researcher, Security Reviewer, and report validation. Each agent card shows its actual state, purpose, latest operation, saved output counts, and an Inspect output action. Counts reflect retained artifacts rather than simulated progress. Failed, skipped, cancelled, and partial work remain distinct.

Workflow opens an interactive map with each stage's input, work, output, and an excerpt from the selected investigation. The retrieval explainer describes primary-source discovery, passage grounding, and citation checks. This implementation ranks bounded passages in Python; it has no embedding index or vector database.

The inspector shows selected source code, verified observation IDs and line ranges, associated external passages, and accepted reviewer recommendations. Missing associations stay explicitly absent. Selecting a graph node never runs target code or performs another model request.

The timeline consumes existing server-sent activity events. The original CSS luminance treatment highlights active operation text while the event connection is open. It stops for completed, partial, failed, and cancelled jobs or a disconnected stream. A last-update counter reports event freshness; it is not provider token streaming or private model reasoning. The animation is disabled by `prefers-reduced-motion`.

The reviewer tray reflects the actual reviewer stage. A prominent outcome panel distinguishes a complete investigation from a partial report, failure, or cancellation. Report actions become available only when a saved report exists; partial reports explicitly direct users to their limitations. The same report action is available beside the live timeline.

After a terminal result, New investigation receives a subtle rectangular purple pulse. Reduced-motion users receive a static highlight. Selecting it resets the completed workspace and focuses a fresh URL input. During an active run it opens the form without cancelling or detaching that run. History, rejected matches, cancellation, offline examples, and report/JSON exports remain accessible.

![Square graph with live investigation and evidence on the right](assets/investigation-layout.png)

![Interactive workflow and retrieval grounding](assets/workflow-explainer.png)

## Local history and research cache

Manage history & cache is available beside recent investigations and in Local workspace. The dialog shows stored investigation/event counts and cache size. Users can clear history (including saved reports, artifacts, and events), the research cache, or both. It requires typing `CLEAR` and blocks deletion while any investigation is queued, running, or cancelling, including jobs outside the latest 50 displayed records.

`GET /api/storage` returns counts. `POST /api/storage/clear` requires the existing same-origin request token, an explicit `history`, `cache`, or `all` scope, and `confirmation: "CLEAR"`. Job submission and cleanup share a lock. Cache cleanup only removes owned digest-named cache files and temporary entries; it skips symlinks and unrelated files. SQLite history is transactionally removed and compaction is attempted. This is application cleanup, not a forensic erasure guarantee.

There is no separate agent memory or vector database. Cleanup preserves credentials, model settings, repository files, and exports saved outside the application's history. Deletion has no application undo.

## Verification

- 111 Python tests pass, including same-origin serving of the graph asset and eight storage cleanup tests covering scope isolation, active-job guards, request protection, and unrelated-file preservation.
- Nineteen dependency-free Node tests cover file provenance, preparation events, technology citations, absent incident matches, accepted finding associations, bounded trees, stable finite layouts, score boundaries, orphan filtering, force stability, drag offsets/cancellation, cursor-anchored zoom, two-pointer pinch calculations, empty-graph idling, and 2× pixel-density sizing.
- Browser checks exercised graph search and selection, evidence mode, offline execution, report tabs, active status animation, cancellation, and terminal animation cleanup. CVSS groups, heatmap, numeric thresholds, CVE search, display options, and force reset were also checked using a clearly labeled synthetic local fixture. No browser console errors were observed during these checks. Pointer drag/cancellation and pinch geometry are covered by deterministic handler tests; physical multi-touch hardware has not been tested.
- Responsive controls and a populated 390px-wide viewport are checked for horizontal overflow. Desktop and mobile screenshots were captured from the implementation under `docs/assets/investigation-*.png`.
- The revised experience was checked with a complete offline run: all three role states, actual operation events, report access, terminal animation cleanup, and the fresh-investigation reset. The storage dialog's confirmation behavior was checked without deleting user history; deletion tests used disposable fixtures.
- UI verification used an isolated local SQLite store with saved public review artifacts and offline fixtures. It consumed no hosted-model or GitHub quota and did not modify existing review records.

The animation is an original CSS implementation of the requested luminous progress treatment; React Bits Pro source was not copied or bundled. Mockup graph labels and illustrative connections are not hardcoded into real reviews. Actual layouts depend on the inspected repository.
