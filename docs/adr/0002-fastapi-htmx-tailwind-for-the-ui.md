---
status: accepted
date: 2026-10-06
---

# FastAPI, HTMX and Tailwind for the UI

The UI is a server-rendered FastAPI app with Jinja2 templates, HTMX for interactivity and Tailwind CSS for styling.
The prototype is mostly ranked lists, detail views and review-state forms, which server-rendered HTML fragments handle with little code and full control over how the demo looks.
This ADR covers the technology only; which pages exist and how they look is still undecided.

## Versions (checked 2026-10-06)

- `fastapi[standard]` 0.142.x, which brings Jinja2 and uvicorn.
- htmx 2.0.x, vendored as a static file.
- Tailwind CSS 4.3.x through the standalone CLI from `tailwindlabs/tailwindcss` GitHub releases, so no Node is needed.

## Considered options

- **Streamlit** (the `NoSkill` branch plan): fastest first screen, but every interaction reruns the whole script, which makes the human-review workflow awkward, and the demo looks generic.
- **htmx 4.0**: stable since 2026-08-28, but only weeks old with changed defaults; 2.0.x is still maintained and has far more examples and docs, which matters in 48h.
- **Tailwind Play CDN**: meant for prototyping only and compiles in the browser at runtime.

## How to use it

- Keep the AI and ranking logic in plain Python modules; routes stay thin and only call them.
  The benchmark and tests call the same modules directly, never through HTTP.
- Routes for HTMX requests return HTML fragments, not JSON; the UI needs no separate JSON API.
- Each review-state change is a small form that swaps only the affected element, for example `hx-post` to the item's state route with `hx-target` on its card.
- Slow LLM calls show progress with `hx-indicator`; switch to the SSE extension only if waiting hurts the demo.
- Templates use a base layout plus partials, so a full page and its HTMX fragment render from the same partial.
- Vendor `htmx.min.js` and the built CSS under `static/`, so the demo does not depend on a CDN.
- Tailwind 4 is configured in CSS (`@import "tailwindcss";`), not in a `tailwind.config.js`; build with `--minify` for the demo and `--watch` while developing.

## Sources

- https://fastapi.tiangolo.com/
- https://htmx.org/docs/#installing
- https://github.com/bigskysoftware/htmx/releases
- https://github.com/tailwindlabs/tailwindcss/releases
