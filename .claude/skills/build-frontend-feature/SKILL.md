---
name: build-frontend-feature
description: Implement one frontend vertical slice (screen/feature) once a CodeAtlas frontend exists. Usage: /build-frontend-feature <screen-or-feature-name>, e.g. /build-frontend-feature dashboard.
---

# build-frontend-feature

Implement exactly one screen or feature in the CodeAtlas frontend, once
one exists in this repository. V1 of CodeAtlas is CLI/library-only (see
`ARCHITECTURE.md` §2) — if no frontend directory exists yet, stop and
report that back instead of scaffolding one on your own initiative; a
new frontend is an architecture-level decision, not a vertical slice.

## Steps (once a frontend exists)

1. **Inspect the existing frontend** first: component structure, state
   management, API/data-fetching conventions, styling approach. Identify
   the closest existing screen/component to copy the pattern from.
2. **Follow existing conventions** — component naming, file layout,
   design system usage. Do not introduce a second pattern for something
   the frontend already does one way.
3. **Implement only the requested screen/feature.** No unrelated
   refactors of surrounding components.
4. **Handle all real states**: loading, empty, error, and success. A
   feature that only renders the happy path is incomplete.
5. **Use real data contracts** — whatever the backend/CLI/API actually
   returns (e.g. the `ProjectKnowledge`/report JSON shape), not an
   invented shape. If the contract doesn't exist yet, say so and propose
   the minimal addition rather than fabricating fake response data.
6. **Avoid fake production behavior**: no hardcoded sample data standing
   in for a real data source, no silently-mocked API calls left in place
   as if they were real integrations.
7. **Add appropriate tests** (component/unit, and integration if the
   project has a pattern for that).
8. **Verify**: run the frontend's build/lint/test commands and actually
   exercise the feature (dev server + manual check, or an automated
   check) before reporting it done.

## Report

State clearly which states were implemented and verified, and flag
anything left using placeholder/mock data as explicitly unfinished.
