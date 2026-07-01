# Placeholder UI Handoff Contract

This document defines what can be replaced by the undergrad UI rewrite and what is fixed backend contract.

## Replaceable Surfaces

- `ui/templates/ui/**`
- `ui/static/ui/**`
- Presentation-only template logic in `ui/views.py` context shaping

## Non-Replaceable Surfaces

- URL contracts:
  - `/ui/intake/new`
  - `/ui/intake`
  - `/ui/intake/<id>`
  - `/ui/intake/<id>/review`
  - `/ui/projects/pre-acq`
- API contracts:
  - `/api/intake-requests/`
  - `/api/intake-requests/<id>/review/`
  - `/api/intake-requests/<id>/promote/`
- Intake state machine:
  - `submitted -> in_review/rejected`
  - `in_review -> approved/rejected`
  - `approved/rejected` terminal
- Permission rules:
  - Submit allowed to scoped lab members (including collaborator)
  - Review and promotion restricted to PI/admin
  - All operations lab-scope constrained unless admin
