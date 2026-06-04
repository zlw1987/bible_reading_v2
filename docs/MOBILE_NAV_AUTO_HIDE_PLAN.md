# Mobile Nav Auto-Hide Plan

## 1. Purpose

This document plans mobile-only header auto-hide behavior for the CMS navigation.

It is planning guidance only. It does not authorize implementation, template changes, CSS changes, JavaScript changes, tests, desktop navigation changes, church structure work, consumer migration, audience filtering, or Community Activities.

`docs/UI_UX_GUARDRAILS.md` remains the UI/UX baseline for normal-user and staff/admin surfaces. Normal-user UI must not expose internal implementation terms.

## 2. Desired Mobile Behavior

On mobile widths:
- Scrolling down hides the header after a small threshold.
- Scrolling up shows the header.
- Near the top of the page always shows the header.
- Any open nav dropdown or staff menu forces the header visible.

The intent is to recover vertical space while reading or scanning content, without making navigation feel unstable when users are interacting with menus.

## 3. Dropdown Preservation Rules

The current dropdown open/close behavior remains the source of truth. Auto-hide must layer around that behavior, not replace it.

Rules:
- Auto-hide is disabled while any dropdown or staff menu is open.
- Opening a dropdown forces the header visible before or at the same time the menu opens.
- Closing the final open dropdown restores normal auto-hide behavior.
- The header must not hide while focus, pointer, or touch interaction is inside the header or any open menu.
- Existing click, tap, focus, escape-key, outside-click, and staff/admin menu behavior should remain aligned with the current implementation.
- Staff/admin dropdown behavior may be more complex than normal-user nav and must remain stable.

If current dropdown behavior has edge cases, those edge cases should be documented before changing auto-hide logic. This plan should not be used to redesign menus.

## 4. Desktop Non-Goals

This work must not change:
- Desktop hover behavior.
- Desktop dropdown timing or positioning.
- Navigation information architecture.
- Menu labels or grouping.
- Staff/admin menu design.
- CSS framework or layout system.

Desktop behavior should be verified as unchanged after implementation, but the feature target is mobile only.

## 5. JavaScript State Rules

Recommended state model:

### Closed / No Menu

Default mobile state when no dropdown is open.

Behavior:
- Track the last scroll position.
- If the user scrolls down beyond the threshold, add the hidden class.
- If the user scrolls up beyond the threshold, remove the hidden class.
- If the page is near the top, remove the hidden class.

### Dropdown Open

State while any nav dropdown or staff menu is open.

Behavior:
- Force the header visible.
- Suspend scroll-driven hiding.
- Preserve the current dropdown source-of-truth logic for open and close.
- Keep the header visible while focus or touch remains inside the menu.
- On close, transition back to either top-of-page or closed/no-menu state.

### Top Of Page

State when the scroll position is near the top.

Behavior:
- Always show the header.
- Ignore hide requests until the user scrolls beyond the top threshold.
- Use a small top threshold so natural scroll bounce does not hide the header immediately.

### Scroll Threshold

Use thresholds to avoid jitter:
- Minimum scroll delta before changing visibility.
- Top-of-page threshold where the header is always visible.
- Optional minimum scroll position before hiding can begin.

The exact values should be chosen during implementation after checking the current header height and mobile scroll feel.

### Reduced Motion

When `prefers-reduced-motion: reduce` is active:
- Preserve the same visible/hidden state rules.
- Avoid animated movement or use an effectively instant transition.
- Do not disable functional auto-hide solely because reduced motion is enabled.

## 6. CSS Expectations

Expected CSS shape:
- Use a class on the header or body to represent hidden state.
- Hide/show with `transform`, such as translating the header out of view.
- Avoid layout jump by keeping the header in the normal fixed/sticky positioning model used by the current implementation.
- Preserve existing dropdown positioning relative to the header.
- Ensure open menus are not clipped by the hidden state.
- Keep z-index behavior compatible with the current mobile header and dropdown stack.
- Keep tap targets and labels readable according to `docs/UI_UX_GUARDRAILS.md`.

Implementation should avoid broad selector rewrites, CSS framework migration, or redesigning the nav surface.

## 7. QA Checklist

Mobile checks:
- iPhone-width normal-user nav: scroll down hides header, scroll up shows header.
- Near top: header remains visible.
- Normal-user dropdown: opening forces header visible.
- Staff/admin dropdown: opening forces header visible and preserves current open/close behavior.
- Open dropdown then scroll: header remains visible and menu behavior remains stable.
- Close dropdown then scroll: auto-hide resumes.
- Touch/focus inside menu: header does not hide.
- EN/ZH nav labels: labels remain readable and do not expose implementation terms.
- Keyboard/focus sanity where applicable: focus does not disappear into a hidden header or open menu.

Desktop regression checks:
- Desktop hover behavior unchanged.
- Desktop dropdown positioning unchanged.
- Desktop navigation IA unchanged.

## 8. Recommended Implementation Slice

Recommended slice name:

`mobile-header-auto-hide-dropdown-safe`

The slice should include mobile-only JS state handling, minimal CSS class support, and focused QA around dropdown preservation. It should not include navigation redesign, staff menu regrouping, church structure work, consumer migration, audience filtering, or Community Activities.
