# UI/UX Design Standards

## Main Objective

Build interfaces that feel thoughtfully designed for this specific product. Prioritize usability, visual hierarchy, product identity, and consistent behavior over decorative effects or design trends.

The result must look and behave like real production software, not a generic AI-generated template.

## 1. Understand Before Coding

Before changing the UI:

- Identify the screen's purpose, target user, main task, and desired outcome.
- Inspect the existing app, routes, components, design tokens, fonts, and dependencies.
- Reuse the existing design system when it works. Improve it when necessary.
- Understand the product's actual features and data. Do not invent features, statistics, testimonials, or interface content to fill space.
- Choose a clear visual direction that fits the product, audience, and use case.

Do not start by generating a generic page shell and filling it with cards.

## 2. Give the Product a Distinct Identity

Make intentional decisions about:

- Typography and text hierarchy.
- Primary, supporting, and accent colors.
- Spacing, alignment, and information density.
- Layout and content grouping.
- Borders, surface contrast, shadows, and corner radii.
- Iconography, illustrations, and motion.

Use one coherent visual language across the application.

Create distinction through meaningful layout, content, typography, and detail. Do not depend on effects alone to make a screen look impressive.

Choose a signature design detail only when it strengthens the product's identity. Do not combine multiple visual trends simply because they are popular.

## 3. Avoid Generic AI Design Defaults

Treat these as warning signs. Use them only when they serve a clear design purpose:

- Purple-to-blue gradient backgrounds and gradient headline text by default.
- Neon glows, decorative light effects, or glassmorphism without a functional reason.
- A centered headline, two generic buttons, a logo row, and three identical feature cards on every landing page.
- Oversized rounded containers, cards nested inside cards, or pills used for ordinary labels.
- Repeated icon boxes with the same title-and-description layout.
- Decorative badges, colored side borders, fake statistics, and meaningless dashboard charts.
- Huge empty spaces that make real tasks harder to reach.
- The same card grid repeated throughout the entire application.
- Emojis used as a substitute for a consistent icon system.
- Excessive shadows, borders, background changes, hover effects, and entrance animations.
- Generic copy such as "Unlock your potential", "Transform your workflow", and "The future of productivity".
- The same typography, spacing, surface treatment, and layout for every type of product.

Do not blindly ban a font, color, radius, card, gradient, or animation. Keep it when it fits the brand and has a clear purpose.

Do not fix a generic interface by merely changing its primary color or font. Reconsider the structure and hierarchy.

## 4. Design the Actual User Task

Every screen must make these things clear:

- Where the user is.
- What information matters most.
- What action the user should take next.
- What happens after that action.

Prefer direct actions, descriptive labels, sensible defaults, and minimal friction.

Use progressive disclosure for secondary options. Avoid unnecessary confirmation steps, competing primary buttons, hidden controls, and decorative elements that push important content aside.

Marketing pages and internal application screens have different needs. Use storytelling and a strong hero when they help explain a product. Inside dashboards and workspaces, prioritize the user's task, real content, navigation, and relevant controls.

## 5. Use Layout and Visual Hierarchy Intentionally

- Establish a clear relationship between page titles, section headings, body text, metadata, and actions.
- Use a consistent spacing scale and align related elements.
- Adjust information density to the task. Data-heavy tools need efficient layouts. Editorial pages need comfortable reading space.
- Use cards only when grouping information or actions improves understanding.
- Prefer simple surfaces, subtle separators, and restrained shadows when they communicate structure clearly.
- Use a consistent radius scale instead of rounding everything equally.
- Choose typography for readability and character. Do not select a trendy font without considering the product.
- Use color to communicate brand, hierarchy, status, and interaction.
- Keep charts, tables, forms, and lists easy to scan.

Every major visual element must serve content, navigation, feedback, or brand identity.

## 6. Make the Interface Feel Natural

- Use plain, product-specific language.
- Name real tasks, objects, outcomes, and constraints.
- Avoid vague marketing statements and repetitive AI-style copy.
- Give controls clear labels and meaningful feedback.
- Use subtle, purposeful motion that explains a change or provides feedback.
- Avoid bouncing, scaling, glowing, or revealing every element merely to make the interface feel dynamic.
- Respect reduced-motion preferences.
- Make interaction states consistent throughout the application.

The interface should feel responsive and human-centered without trying too hard to look futuristic.

## 7. Handle Real Product States

Do not design only for the perfect screenshot.

Implement and review relevant states, including:

- Loading and pending operations.
- Empty data and first-time use.
- Errors with clear recovery actions.
- Invalid inputs and validation feedback.
- Disabled, selected, active, hover, and keyboard-focus states.
- Success feedback and destructive-action confirmation.
- Long text, large data sets, missing images, and unavailable content.
- Permission restrictions and expired sessions where relevant.
- Narrow screens, touch input, and responsive navigation.

All visible controls must perform their stated actions. Do not use fake charts or sample metrics as substitutes for real functionality.

Keep spacing, typography, controls, and feedback consistent across pages.

## 8. Accessibility and Responsive Design

- Use semantic HTML and appropriate form labels.
- Support keyboard navigation and visible focus indicators.
- Maintain readable contrast and legible text sizes.
- Provide accessible names for icon-only controls.
- Do not communicate status through color alone.
- Make interactive targets practical for touch.
- Prevent clipped text, overlapping controls, and horizontal overflow.
- Test narrow layouts instead of merely shrinking the desktop interface.

Aim for WCAG 2.2 AA where applicable.

## 9. Follow the Existing Technical Architecture

- Preserve the existing framework, conventions, and working functionality.
- Use installed components and libraries when they fit the design.
- Avoid adding dependencies for effects that simple CSS can handle.
- Keep shared components and design tokens consistent.
- Do not rewrite unrelated parts of the application.
- Do not sacrifice performance or accessibility for visual effects.

## 10. Review Before Finishing

After implementation, inspect the actual rendered interface when browser or screenshot tools are available. Do not judge quality from source code alone.

Apply these checks:

1. Product-specificity test:
   Could this interface belong to almost any other product if the logo and colors changed? If yes, make its structure and content more specific.

2. Decoration-off test:
   If gradients, shadows, glows, badges, and animations disappeared, would the hierarchy and layout still make sense? If not, improve the underlying design.

3. Real-content test:
   Do the layout and controls work with actual product data, long text, empty results, and errors?

4. Consistency test:
   Do navigation, typography, spacing, buttons, forms, and feedback follow the same design system across screens?

5. Task-completion test:
   Can users understand the page, find the main action, complete the task, and recover from common errors?

6. Responsive and accessibility test:
   Check relevant viewport sizes, keyboard interactions, focus states, contrast, and reduced motion.

Fix meaningful problems before declaring the work complete. Prefer a few precise improvements over adding more decoration.

## Final Standard

A successful interface does not need to look trendy, futuristic, minimal, or luxurious.

It needs to look intentional, fit its product, communicate clearly, behave consistently, and make the user's task easier.
