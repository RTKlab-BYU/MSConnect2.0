---
name: web-design-guidelines
description: Review MSConnect pages for responsive behavior, accessibility, and interaction clarity.
---

# MSConnect web interface review

For a UI review, first fetch the current upstream rules and apply them to the specified files. Keep findings concise and actionable.

Upstream guidelines: [Vercel Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)

Project review additions:

- Check keyboard navigation, focus visibility, accessible names, loading/error/empty states, and status communication beyond color.
- Check 1280×720, 1440×900, and a narrow mobile viewport at 100% zoom.
- Confirm the document itself does not overflow horizontally and that dense data remains searchable or paginated.
- Report findings as `file:line — issue — suggested fix`; distinguish a real defect from a preference.

## Upstream attribution

Workflow reference: [Vercel web-design-guidelines skill](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines). Its instructions point to the upstream Web Interface Guidelines URL above for the current review rules. This local file links to the source and adds MSConnect-specific checks; it does not reproduce upstream guideline content.
