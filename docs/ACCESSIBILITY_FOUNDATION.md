# Member Accessibility Foundation

Use one page-level `h1`, followed by headings that reflect real sections. The
shared shell provides a focus-visible skip link, a labeled primary navigation,
one focusable `main` landmark, and a footer landmark. Do not add another
`main` element inside page templates.

Use the existing `.button`, `.button-secondary`, and `.button-danger` classes
only for actions; keep ordinary inline links as links. Icon-only controls need
an accessible name, while decorative icons and SVGs use `aria-hidden="true"`.
Status badges must include meaningful text and may use `.status-good`,
`.status-warning`, `.status-danger`, or `.status-neutral`.
Secondary buttons and form controls use a darker boundary so their shape stays
visible against white cards; the existing brand and status colors are retained
because their text contrast remains readable and their meaning is never
color-only.

Forms should keep visible labels, help text, field errors, and non-field
errors. Member forms with several fields can include
`shared/_form_error_summary.html`; its links target the invalid controls and
the shared shell focuses it after an invalid response. Keep field-level errors
visible as well. The initial examples are Profile, Prayer creation/editing,
reflection editing, and the Reading guide form.

Keyboard focus must remain visible. Custom navigation surfaces close with
Escape, restore focus to their toggle, and lock background scrolling only
while open. Native `details` controls should remain native.

Shared motion is disabled under `prefers-reduced-motion: reduce`. New
transitions or smooth scrolling must respect the same preference. Long
English and Chinese labels should wrap, action rows should wrap on narrow
screens, and genuinely wide tables should use `.table-scroll`.
