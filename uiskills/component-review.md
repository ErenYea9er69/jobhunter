---
name: component-review
description: "Plan and asset review checkpoint for comp-led builds before page code exists."
---
# Plan and asset review

Use this checkpoint on comp-led builds once every raster region has its assets and plan prepared, before any page code exists. The approved comp is the reference. The user reviews two things: the assets/plates that will ship, and the production plan for everything else (meaning which regions code draws). A painted region planned as code is the most expensive mistake a comp-led build makes, and this is where the user catches it. Text, controls and chrome are judged later, in the assembled first viewport.

## Plan, capture, and review

1. Prepare the component plan from the measured spec, comp, and asset files.
2. Present the review to the user directly, showing the assets and production plan for confirmation.
3. Wait for the user's explicit review and decisions before building past this checkpoint.

## Act on feedback

Apply the user's decisions as given, never your own favorable verdict in their place:

- **approve**: once every item is approved and the inventory is confirmed, advance to the hero viewport.
- **revise** (an asset/plate): regenerate that asset at the same path with the user's feedback.
- **revise with split** (an asset): replace that region with its distinct layers (e.g., frame plate with a transparent opening, content image, moving parts). Name each layer clearly after the original region.
- **revise** (a plan item): adjust the regions plan as the feedback says (resize or extend a raster region, split material into its own region, or adjust the code region).
- **reclassify** (a code region): change that region's kind to the one the user chose and update the description of the material.
- **missing**: add the missing region to the plan and produce its asset if it is raster.

Unchanged decisions carry over, so the user reviews only what changed. Any spec change or replaced asset needs confirmation before the build phase proceeds.

## Assemble and review

Build the first viewport from the approved assets and plan. Present the assembled first viewport to the user for visual confirmation before continuing with the rest of the surface.

- Use the approved comp as reference.
- Present the assembled preview and dependencies.
- Needs-work feedback starts another refinement round.

Acceptance closes asset/layout review for this build:
- Complete the rest of the page, responsive behavior, finish checks, and documentation with the accepted first viewport as the visual direction.
- Preserve the accepted direction; a later explicit user change is treated as a new task.
