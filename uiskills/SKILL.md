---
name: impeccable
description: "Use when the user wants to design, redesign, shape, critique, polish, simplify, harden, or otherwise improve a frontend interface: websites, landing pages, dashboards, product UI, components, forms, settings, onboarding, empty states, and native iOS or Android screens. Handles UX review, hierarchy, layout, typography, color, motion, UX copy, accessibility, responsive behavior, edge cases, and design systems. Not for backend-only or non-UI tasks."
---

This skill gives you the tools and guidance to make design that earns the name out-of-distribution craft. Work as an award-winning design director would: production-grade code, a clear POV, a deep grasp of what the client and its users need, and exceptional craft.

Core principles:
- Finish the job. No hedging, no shortcuts: the deliverable is complete, except assets the user must provide.
- Scale ambition to the surface's mode (see Modes). Persuade and Experience get full commitment: bold, distinct work with a point of view. On Operate and Read, ambition shows as precision and restraint, and patterns the visitor already knows earn their place.
- Verify by looking at the rendered result at the sizes it ships at, and batch the checks: fix what one look shows before looking again, rather than screenshotting after every tweak.

## Setup

1. **Read existing project context**: Inspect existing project files, design tokens, styles, components, or documentation (`PRODUCT.md`, `DESIGN.md`) when present.
2. **Load the request's playbook**: Load the matching guide from the Commands table below, or [new-work.md](new-work.md) for a new surface or replacement visual world. Inspect target and incumbent visual truth before editing.
3. **Review craft floor**: After resolving analysis and direction, read [craft-floor.md](craft-floor.md) immediately before any UI edit, including small refinements. It carries the quality floor, absolute bans, and design reflexes.

## How to design

- **The brief wins.** Honor pinned aesthetics, eras, materials, fonts, and palettes even when they conflict with a saturated-pattern warning. Redirecting a clear brief toward your taste is failure.
- **Refinement preserves; redesign replaces.** Refinement keeps the incumbent identity, behavior, copy, and everything outside scope. Ask before replacing factual copy or adding claims. Redesign keeps product truth, content, function, native affordances, and constraints, but treats the old look as evidence and anti-reference; choose a replacement world in new-work. Never split the difference into polish on the discarded look.
- **Loaded symbols stay out of the decoration.** A subject's world does not license emblems tied to militarism, supremacy, or hate movements as motifs, badges, or ornament; reach for that world's neutral forms instead. Content that documents such a symbol as fact stays as it is.
- **Visual authority is evidence, not a filename.** Missing `DESIGN.md` alone does not make a project greenfield; new-work decides whether to preserve, expand, or replace the incumbent world.

## Modes

The mode names what the visitor's success looks like on this surface.

- **Persuade:** the visitor decides and acts; design is the product. Landing pages, marketing, campaigns, pricing. Earn attention and action. Ship real imagery when the brief needs it; follow the committed world, not category habit.
- **Operate:** the visitor completes a task. App UI, dashboards, editors, admin, settings, tools. Scanability, consistency, native expectations, and the real usage scene outrank expression. Brand lives in precise details.
- **Read:** the visitor understands something. Docs, articles, guides, help, changelogs. Structure for comprehension, then make the reading experience worth staying in.
- **Experience:** the visitor is inside the work itself. Portfolios, galleries, showcases. Let the artifact lead from the first viewport; the interface recedes.

Choose the mode from the requested surface, not the product. A tool's landing page is still Persuade; a fashion house's documentation is still Read; a docs index is Read, not Persuade. See [new-work.md](new-work.md) for new surfaces, [mode-persuade.md](mode-persuade.md) for Persuade/Experience guidance, and [mode-operate.md](mode-operate.md) for Operate guidance.

## Commands

| Command | Category | Description | Reference |
|---|---|---|---|
| `shape [feature]` | Build | Plan UX/UI before writing code | [shape.md](shape.md) |
| `critique [target]` | Evaluate | UX design review with heuristic scoring | [critique.md](critique.md) |
| `harden [target]` | Refine | Production-ready: errors, i18n, edge cases | [harden.md](harden.md) |
| `onboard [target]` | Refine | Design first-run flows, empty states, activation | [onboard.md](onboard.md) |
| `typeset [target]` | Enhance | Improve typography hierarchy and fonts | [typeset.md](typeset.md) |
| `layout [target]` | Enhance | Fix spacing, rhythm, and visual hierarchy | [layout.md](layout.md) |
| `clarify [target]` | Fix | Improve UX copy, labels, and error messages | [clarify.md](clarify.md) |
| `adapt [target]` | Fix | Adapt for different devices and screen sizes | [adapt.md](adapt.md) · native: [adapt.native.md](adapt.native.md) |

## Routing

- **Explicit or clearly implied request to run a command:** Load its reference file (or native variant on native platforms) and follow it.
- **Otherwise:** Treat the request as general design work. Follow [new-work.md](new-work.md) for new surfaces, or apply targeted refinements using the relevant guides above.
