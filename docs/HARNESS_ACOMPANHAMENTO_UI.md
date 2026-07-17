# Harness — Acompanhamento

The Harness Hub presents several local projects as a single accompaniment
workspace for people who do not need to read code or terminal output.

## Product contract

- The overview makes every project's state, current implementation and active
  task understandable within a few seconds.
- Progress is factual: task position, completed/current/waiting counts and one
  of five named stages. The interface never invents a percentage.
- Project details explain what is happening, why it matters, the expected
  result, the last update and what remains.
- Attention, stale, completed and unavailable states use explicit text in
  addition to color.
- The browser updates locally without changing task data at random and keeps
  the selected project open.
- User-facing copy is Brazilian Portuguese and excludes commands, logs, paths
  and implementation jargon.

## Canonical frontend

The framework-free frontend lives in
`harness_core/dashboard_hub_assets/`. It is used by both delivery paths:

1. `dashboard hub` / `dashboard hub-serve`, through the Python renderer;
2. the Node Hub sidecar, which serves the same assets and `/api/world` data.

`presentation.js` holds the demonstration state and normalizes live snapshots.
`hub.js` renders the overview and project details. `hub.css` owns the responsive
visual system. The Python and Node collectors each add a `presentation` object
to every repository snapshot so the browser receives language intended for
people, not raw operational records.

## Accessibility and responsive behavior

- Semantic regions, a skip link, visible focus and keyboard-operable controls;
- polite live announcements for refresh outcomes;
- status messages that do not depend on color alone;
- reduced-motion support;
- two or three project columns on wide screens and one column on mobile;
- horizontally scrollable filters and a vertical progress journey on mobile;
- no horizontal page overflow.
