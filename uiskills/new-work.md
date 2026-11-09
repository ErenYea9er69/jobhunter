---
name: new-work
description: "Flow for a new surface or replacement visual identity."
---
# New visual work

Use this flow for a new surface or a replacement visual identity. Review existing documentation (such as `PRODUCT.md` or `DESIGN.md`) when available.

## 1. Decide what is already true

Read existing design guidelines, representative code, tokens, components, and assets:

- **Redesign:** preserve product truth, content, function, constraints, and explicit brand commitments; replace the old visual world rather than polishing it. The old look is evidence of what the subject is, not authority over what it becomes.
- **Established world:** inherit it. A missing design document does not erase a coherent identity already in code; document that identity instead of inventing a replacement.
- **Incomplete brand:** preserve confirmed assets and recognizable traits, then expand the system with the user for this surface.
- **No visual authority:** create a new world with the user.

A section, component, feature, or state inside an established surface inherits that surface. Never turn a local addition into a new identity exercise.

## 2. Ask what will change the work

Before implementation, confirm key decisions with the user. Ask two or three related questions; a precise request needs only a compact confirmation. Skip settled facts:

- **Persuade:** who must act, what they should believe, which real proof, content, or assets earn that belief.
- **Operate:** the task, information, important states, frequency, constraints.
- **Read:** the reader's question, source material, structure, wayfinding.
- **Experience:** what leads, how exploration unfolds, which interaction or transition matters.

Across modes, ask what success looks like, what must remain untouched, and what would make a polished result feel wrong. Never ask for raw CSS values or canned aesthetic tropes.

## 3. Choose the right amount of invention

### Extend an existing surface

Inherit its world and composition. Resolve only the new purpose, content, hierarchy, states, interaction, and how the addition joins the surrounding experience.

### Create a whole surface inside an established world

Keep the visual system fixed. Derive three materially different structural compositions from the content, task, and user behavior. Present these distinct structural options to the user to choose from before building.

### Create or replace the visual world

1. Name the product's unique mechanism in one sentence, the audience's real scene, its cultural home, and what this first surface must prove. Identify the generic category default and avoid falling into it.
2. Explore concrete visual systems, artifacts, places, or rituals the audience recognizes. Look at physical objects, historical print, specialized notations, and interfaces.
3. Formulate two or three distinct, fully committed directions. Each direction pairs a coherent visual language (palette, type scale, spatial density) with a concrete first-viewport layout and a signature interaction.
4. Present the directions clearly to the user, highlighting the core thesis, the palette and type choices, and the specific trade-offs of each option.

What the opening must do, and how far the world reaches into the page, depends on the surface's mode:
- For Persuade and Experience surfaces, see [mode-persuade.md](mode-persuade.md).
- For Operate surfaces, see [mode-operate.md](mode-operate.md).

## 4. Commit the world

Pick a color strategy before picking colors:
- **Restrained:** neutrals tinted from the world plus one functional accent. Common on screens people operate or read.
- **Committed:** one saturated color carries 30–60% of the surface.
- **Full palette:** 3–4 named, purposeful color roles.
- **Drenched:** the surface itself is the color.

Color commits at page scale: fields that own whole regions, not accents scattered timidly over a neutral ground.

Choose typography with character suited to the mode:
- Operate and Read surfaces excel with robust system stacks and workhorse UI typefaces.
- Persuade and Experience surfaces demand typefaces with a distinct point of view. Avoid overused generic tropes (e.g., defaulting to warm cream backgrounds with high-contrast serif display fonts).

## 5. Record the direction contract

Before code, record the chosen direction clearly:
- **THESIS:** The core idea this surface owns and the generic arrangement it refuses.
- **OWN-WORLD:** The palette and component language, specific enough to be recognizable with all text removed.
- **STORY:** What the visitor understands, believes, and does.
- **FIRST VIEWPORT:** The exact composition, hierarchy, and primary action placement.
- **SIGNATURE MOMENT:** The central interaction, transition, or reveal.

For planning-only tasks, return the selected direction to [shape.md](shape.md).

## 6. Build with full commitment

Build the agreed direction, not a diluted interpretation. Commit every detail: navigation, buttons, inputs, tables, and links must speak the chosen design language.

### Core building disciplines

- **The first viewport is a thesis, not a header.** Demonstrate the mechanism immediately at scale; do not trap the concept inside a standard hero card.
- **Prove, don't claim.** Show the interface at work with realistic demonstration data; author realistic content instead of placeholder copy.
- **Author the assets.** Real designs require crafted imagery, textures, icons, and diagrams. Never substitute decorative CSS gradients where an authored asset belongs.
- **Pace the scroll.** Vary density, scale, imagery, and breathing room. Keep one cohesive spacing rhythm throughout, with more space above a heading than below it.
- **Orchestrate motion.** Give the surface purposeful, native-feeling motion once, rather than scattered, gratuitous hover effects.

For component and asset planning on complex layouts, consult [component-review.md](component-review.md).

## 7. Inspect and finish

Inspect the surface across its target sizes in a batched verification pass:
- On the web: inspect desktop (1440px) and mobile (390px) viewports. Check interactive states (hover, focus, active, loading, empty, error) and layout responsiveness.
- On native platforms: follow the platform conventions in [ios.md](ios.md) and [android.md](android.md).
- Verify against the quality floor in [craft-floor.md](craft-floor.md).
- Verify accessibility: contrast ratios (≥4.5:1 for body text, ≥3:1 for large text), legible type scale, usable touch targets (≥44px web, ≥48dp Android), and logical focus order.

Complete any necessary adjustments in a single focused batch, verify the final result, and deliver the completed surface to the user.
