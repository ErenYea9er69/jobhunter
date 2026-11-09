---
name: doctor
description: "Report and repair drift between project design artifacts and the current codebase."
---
# Project Design Health Check

Report and repair drift between project design artifacts and the current codebase (e.g. `PRODUCT.md`, `DESIGN.md`, design tokens, and components).

This is maintenance, not redesign. Do not redesign anything, do not open files outside the ones the check identifies, and do not make changes without explicit user approval.

## What this owns

Three kinds of drift travel under "out of date":

- **Schema drift.** An artifact contains deprecated fields, unused keys, or files in retired locations.
- **Truth drift.** The codebase has evolved and the documentation or design tokens no longer accurately describe it.
- **Platform alignment.** A workspace carrying native build files (iOS / Android) while inheriting web configuration, leading to mismatched platform guidance.

## Step 1: Inspect the Project

Review the workspace for key design artifacts:
1. Check `PRODUCT.md` and `DESIGN.md` if present.
2. Check for token definitions, theme files, and shared component directories.
3. For mobile / native apps, verify native conventions ([ios.md](ios.md) and [android.md](android.md)).

## Step 2: Report Findings

Report findings clearly by severity:
- **Obvious fixes**: Unused deprecated fields or wrong paths.
- **Observations**: Areas where recent code changes deviate from documented design rules.
- **Gaps**: Missing design tokens or component definitions that should be clarified with the user.

## Step 3: Truth Drift Restraint

A commit count or code change is not automatically a contradiction. Read design guidelines against the current tokens and components and evaluate based on actual usage.
