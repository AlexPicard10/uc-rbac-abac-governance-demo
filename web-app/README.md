# Governance Demo — explainer web app

A small, **self-contained** single-page slide deck that explains the Unity Catalog
RBAC + ABAC demo scenario: the two synthetic domains, the three assumable roles, the
FR + BE ABAC row filter, and how Genie and Discover respect the same rules.

**Zero build, zero dependencies.** It's one static `index.html` (inline CSS + a little
vanilla JS; fonts load from Google Fonts). Styled to echo the Retail Energy demo app.

## Open it

Just open the file in a browser:

```bash
open web-app/index.html        # macOS
```

Or serve the folder (nicer for the shareable URL / fonts):

```bash
cd web-app && python3 -m http.server 5175   # then visit http://localhost:5175
```

## Navigate

Arrow keys ← → (or Space / PageUp-Down / Home / End), the bottom slide navigator, or
the top nav. Seven slides: Intro → Two domains → RBAC → ABAC → Genie & Discover →
Demo flow → Takeaway.

It's a static explainer — no backend, no workspace connection; all figures are
illustrative of the synthetic demo. The deployment/validation itself lives in the repo
root (`driver/`, `sql/`, `docs/`).
