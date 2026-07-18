# Retired UI Handoff Contract

The Django-template UI has been retired. This document records the former replacement boundary and the backend contracts that remain active.

## Replaceable Surfaces

- `ui/templates/ui/**` removed
- `ui/static/ui/**` removed
- `/ui/*` URL contracts now redirect to `/app/*`

## Non-Replaceable Surfaces

- Redirect compatibility:
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
