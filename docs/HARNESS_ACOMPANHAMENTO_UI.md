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
- User-facing copy is Brazilian Portuguese and excludes commands, logs and
  implementation jargon. Filesystem paths appear only in the explicit folder
  management dialog, where they are necessary for the user's choice.

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

## Folder management

The header action **Gerenciar projetos** opens a keyboard-accessible dialog
backed by the same local-only token used by the dashboard. It can add an
existing folder, hide it from the overview, show it again, or remove it from
monitoring. Removing a folder only updates `.harness/dashboard/hub/repos.json`;
it never deletes the folder or any user file. Folders without Harness data stay
registered and appear as unavailable until they start publishing information.

Both local servers expose the same endpoints: `GET /api/repos` and the local
token-protected actions `POST /api/repos/add`, `/hide`, `/show`, and `/remove`.

## Accessibility and responsive behavior

- Semantic regions, a skip link, visible focus and keyboard-operable controls;
- modal focus containment, Escape-to-close and focus restoration;
- polite live announcements for refresh outcomes;
- status messages that do not depend on color alone;
- reduced-motion support;
- two or three project columns on wide screens and one column on mobile;
- horizontally scrollable filters and a vertical progress journey on mobile;
- no horizontal page overflow.
