# Investigation workbench

The interface implements the approved black, square-edged design with compact typography, thin straight graph connectors, and softly glowing multicolored nodes. It uses the existing HTML, CSS, JavaScript, and same-origin Python API. No React runtime, external font request, or additional package is required.

## Repository graph

- File nodes come from the pinned repository tree and inspected file artifacts. Preparation events reveal successfully read files before the repository artifact is saved.
- Solid lines represent folder membership or grouping of observed technologies. They are not imports, runtime calls, network reachability, or a claim of architectural completeness.
- Evidence mode adds observation and original-report nodes. Dashed lines represent cited associations. A source is connected to repository observations only when an accepted finding references both; retrieval alone does not establish relevance.
- Colors distinguish groups. They do not encode severity, exploitability, or risk. Uninspected files are dimmed; the selected node has an independent outline.
- Inspected files take priority within a 160-file view. Additional observations and technology/source nodes are bounded separately. Omitted tree entries are counted. Full saved artifacts remain available in the Evidence tab and JSON export.
- Search highlights matches; the inspected-only filter removes uninspected file nodes. Select a node to open its inspector. Drag the graph to pan; use +, −, and Fit to zoom. Graph nodes are keyboard buttons, and an expandable text node list provides another way to select them.

## Inspector and live progress

The inspector shows selected source code, verified observation IDs and line ranges, associated external passages, and accepted reviewer recommendations. Missing associations stay explicitly absent. Selecting a graph node never runs target code or performs another model request.

The timeline consumes existing server-sent activity events. The original CSS luminance treatment highlights active operation text while the event connection is open. It stops for completed, partial, failed, and cancelled jobs or a disconnected stream. A last-update counter reports event freshness; it is not provider token streaming or private model reasoning. The animation is disabled by `prefers-reduced-motion`.

The reviewer tray reflects the actual reviewer stage. Report download becomes available only when a saved report exists. History, partial results, rejected matches, cancellation, offline examples, and report/JSON exports remain accessible. A saved review starts with its URL form collapsed; New investigation opens it again.

## Verification

- 100 Python tests pass, including same-origin serving of the graph asset.
- Seven dependency-free Node tests cover file provenance, preparation events, technology citations, absent incident matches, accepted finding associations, bounded trees, and stable finite layouts.
- Browser checks exercised graph search and selection, evidence mode, offline execution, report tabs, active status animation, cancellation, and terminal animation cleanup. No browser console errors were observed during these checks.
- A populated 390px-wide viewport had no horizontal page overflow. Desktop and mobile screenshots were captured from the implementation under `docs/assets/investigation-*.png`.
- UI verification used an isolated local SQLite store with saved public review artifacts and offline fixtures. It consumed no hosted-model or GitHub quota and did not modify existing review records.

The animation is an original CSS implementation of the requested luminous progress treatment; React Bits Pro source was not copied or bundled. Mockup graph labels and illustrative connections are not hardcoded into real reviews. Actual layouts depend on the inspected repository.
