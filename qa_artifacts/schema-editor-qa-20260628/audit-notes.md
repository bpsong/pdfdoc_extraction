# Schema editor QA audit

## Scope

- Target: `http://localhost:8000/app/schemas`
- Requested flow: create, validate, save, reopen, and edit a schema.
- Evidence source for fields: `fts_config org.yaml`.

## Source field model

- `supplier_name`: string
- `purchase_order_number`: string
- `invoice_amount`: float
- `project_number`: optional string
- `line_items`: array of objects
  - `item_description`: string
  - `item_quantity`: float
  - `unit_price`: float
  - `discount`: float
  - `total_amount`: float

## Planned validation checks

1. Create a new YAML schema with all source fields and nested line-item fields.
2. Confirm string fields expose Min length, Max length, Pattern, Placeholder, and Multiline controls.
3. Confirm numeric fields expose Min value, Max value, Step, Decimal places, and Format controls.
4. Confirm array items can be changed to object and accept nested fields.
5. Exercise invalid enum-without-choices, invalid numeric ranges, zero/negative step, invalid decimal places, invalid schema file name, and invalid regular-expression input.
6. Save, reopen, compare the rendered field model, edit one field, save again, and verify persistence.
7. Check keyboard focus order, labels, error announcement, narrow viewport reflow, unsaved-change warning, search, and duplicate-schema handling.

## Blocker

The in-app browser redirects the target route to `/login`. The configured admin password is not present in the runtime YAML and no authenticated browser session is available. The user was asked to sign in in the visible in-app browser, but the browser remained on the login page across three consecutive goal turns. The requested creation, validation, save, reopen, edit, and screenshot evidence cannot be verified until an authenticated admin session exists.

## Evidence limit

Repository inspection establishes the intended controls and server-side validation rules, but it is not visual or behavioral proof of the running page. No product findings should be treated as confirmed until the live flow can be exercised.
