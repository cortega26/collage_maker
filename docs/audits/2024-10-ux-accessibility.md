# UX/UI & Accessibility Review — October 2024

| Severity | Issue | Evidence | Impact | Recommendation | Owner |
| --- | --- | --- | --- | --- | --- |
| S1 | Colour pickers lack accessible state | Caption stroke/fill buttons expose static labels and do not announce the chosen colour or provide descriptions.【F:src/widgets/control_panel.py†L166-L207】 | Screen-reader users cannot confirm colour selection; violates WCAG 2.2 success criterion 3.3.2 (labels/instructions). | Update accessible descriptions when colours change, announce via status bar, and expose swatch preview. | Front-end Lead |
| S1 | Focus order skips size controls | Tab order jumps from visibility checkboxes to font combo then uppercase toggle, skipping slider/spin grouping.【F:src/widgets/control_panel.py†L166-L213】 | Keyboard navigation feels erratic; difficult to adjust font size without mouse. | Set explicit `setTabOrder` chain or wrap groups in `QGroupBox` with descriptive labels. | Front-end Lead |
| S2 | Progress dialog lacks descriptive text | Export progress dialog hides cancel button and shows empty label, so assistive tech hears “Saving collage…” without progress context.【F:src/main.py†L642-L691】 | Users relying on announcements cannot tell whether operation is ongoing or complete. | Provide progress text updates, accessible name, and optional cancel/backoff mechanism. | Product Owner |
| S2 | Template errors silent | `_apply_template` swallows exceptions and fails silently when templates malformed.【F:src/main.py†L349-L356】 | Users receive no feedback when template parse fails; inconsistent UX. | Validate template format, surface inline error, and log invalid entries. | Product Owner |

## Additional Observations
- Control heights meet 36 px guidance, but confirm high-contrast mode compatibility in manual testing.
- Add keyboard shortcuts for colour pickers (e.g., Enter to reopen last dialogue) and provide tooltip with colour preview hex.
