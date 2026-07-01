# Schema Editor QA — 2026-06-28

## Scope

- Surface: `http://localhost:8000/app/schemas`
- Flow: create, validate, save, reopen, and edit a schema derived from `fts_config org.yaml`.
- Capture: Codex in-app browser, desktop viewport unless noted.

## Step 1 — Existing editor state (`01-start.png`)

- Health: usable, with density and scanability risks.
- Strengths: the schema list, field editor, and live YAML preview are visible together; the active schema and primary actions are clear.
- UX/design risk: long field forms become very tall while the YAML preview stays fixed beside them, making cross-checking distant fields cumbersome.
- Accessibility risk: multiple controls repeat generic accessible names such as `Key`, `Label`, `Type`, and `Pattern`; without field-specific grouping or names, screen-reader and voice-control users may struggle to identify the intended field.
- Evidence limit: keyboard focus order and announcements are tested separately below.

## Step 2 — New schema draft (`02-new-schema.png`)

- Health: healthy.
- Strengths: the default filename and title make the next step obvious; Save and Validate are available; the empty state clearly exposes six field-type shortcuts.
- UX risk: Save appears enabled before any fields exist, while the form does not explain whether an empty schema is intentionally valid.
- Accessibility risk: the unsaved marker is only an asterisk prepended to the title; its meaning is not explained in visible copy.
