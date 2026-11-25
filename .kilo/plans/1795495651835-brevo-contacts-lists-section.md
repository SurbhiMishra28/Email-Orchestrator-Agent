# Brevo-style Contacts section (lists as a first-class section)

## Goal

Make the Contacts page match Brevo's information architecture: a **Lists section**
that owns the page, with folders and lists in a left rail, and the selected list's
contacts in the table on the right. A list the user creates (e.g. "Noida") must
appear there and be selectable, exactly as it does in Brevo.

Today lists are a horizontal tab strip above the table (`App.jsx:5117-5170`), which
is what breaks down as lists accumulate and what caused the name/⋮ collision.

## Target layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ Contacts            [Import CSV] [Add contact] [Create a list]        │
├───────────────────┬──────────────────────────────────────────────────┤
│ LISTS             │ Noida   (12 subscribed · 1 unsub · 0 blocked)    │
│  ▸ All contacts   │ [search contacts…]      [Add contacts] [⋯]      │
│  ▸ Eligible       ├──────────────────────────────────────────────────┤
│  ── Folders ──    │ ☑ Contact │ Subscribed │ Blocklisted │ Email │ ⋯ │
│  ▾ Noida (3)      │ … rows …                                         │
│  ▸ No folder (1)  │                                                  │
│  [+ New list]     │                                                  │
└───────────────────┴──────────────────────────────────────────────────┘
```

Left rail = navigation (Brevo's model). Right = the selected list's data.

## Constraints and invariants

- Do not change any API contract. `/api/lists`, `/api/lists/folders`,
  `/api/lists/{id}/contacts` already return everything needed
  (`folder_id`, `folder_name`, `total_subscribers`, `unsubscribed_count`,
  `total_blacklisted`).
- Keep every existing capability: import CSV, add contact, bulk select, add/remove
  from list, remove duplicates, remove from other lists, list settings, rename,
  move, duplicate, delete, eligibility toggle, blocklist toggle.
- Preserve the overlap fix already made (truncate + `shrink-0`).
- Must not regress the 243-test suite.

## Ordered tasks

### 1. Extract the list rail into a component
- Add `ListRail` (module scope, near `ListsView` at `App.jsx:590`).
- Props: `folders`, `lists`, `selectedList`, `onSelect`, `onCreate`, `loading`.
- Renders: "All contacts", "Eligible", a Folders group (each folder with a count),
   "No folder", and a `+ New list` button.
- Each row is a button with `min-w-0` + `truncate` + `title`; counts use
   `tabular-nums`. No absolute-positioned children, so nothing can overlap.

### 2. Replace the tab strip in the Contacts view
- Delete the `<div>` at `App.jsx:5117-5170` (the `seg-item` strip and its per-tab
  ⋮ menu).
- Insert the two-column grid wrapper around the existing right-hand content:
  - Left: `<ListRail/>` in a `Card` with `lg:w-[240px] shrink-0`.
  - Right: the existing context bar, search bar, bulk bar and table, unchanged.
- Move the per-list ⋮ menu into the rail row (or into the right-hand context bar
  as a single `⋯` button for the selected list). The rail row keeps
  `min-w-0` so the name truncates instead of colliding.

### 3. Make the selected list's identity explicit
- In the right-hand context bar, show the selected list's name as a heading plus
  its counts, so the table is unambiguous when the rail is collapsed on mobile.
- Keep the existing counts (subscribed / blocklisted / unsubscribed) sourced from
  the same `lists.find(...)` lookups already in use at `App.jsx:5176-5179`.

### 4. Mobile behaviour
- Below `lg`, the rail becomes a horizontal scroller above the table
  (`flex overflow-x-auto lg:flex-col`), each row `shrink-0`.
- This is the only structural risk: a horizontal scroller must not clip the ⋮
  menu. Render the menu in the right-hand bar on small screens, in the rail on
  large screens.

### 5. Lists page alignment
- `ListsView` (`App.jsx:590`) keeps its folder rail + cards, but reuse `ListRail`
  for the folder column so the two screens cannot drift apart.

### 6. Verification
- `npm run build --prefix frontend` clean.
- `pytest -q` (MySQL) — expect 243 passed; the known
  `test_run_all_drains_a_paced_queue` flake passes in isolation.
- Manual: create folder "Noida" → create list "Noida" inside it → confirm it
  appears in the rail with a count → select it → table shows its contacts →
  reload page → still selected (URL/`selectedList` state).
- Overlap check: create a list with a 40-character name and confirm the name
  truncates and the ⋮ stays clickable.

## Risks

1. **Mobile ⋮ clipping** — mitigated by rendering the menu in the right bar below
   `lg`.
2. **Duplicated rail markup** — mitigated by extracting `ListRail` and using it on
   both Contacts and Lists.
3. **Large list counts** — the rail renders one row per list; Brevo caps at 300,
   and `MAX_LISTS = 300` is already enforced in `lists.py`. No virtualisation
   needed at that size.

## Out of scope

- Changing list/campaign APIs.
- A separate "Segments" screen (Brevo has one; the app models segments as
  eligible/blocklisted filters, which stay as-is).