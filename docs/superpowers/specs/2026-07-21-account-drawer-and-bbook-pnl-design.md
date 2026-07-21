# Account Drawer Stability and Bbook Phase P&L Design

## Goal

Keep account detail drawers mounted when detail data arrives, and make Bbook
selection/validation-period profit, loss, and net P&L visible in both the
overview and user-structure views.

## Current Findings

- `AccountDrawer.vue` places `v-for` and `v-if` on the same `<tr>` for the
  de-extreme rows. Vue evaluates the `v-if` before the loop variable is in
  scope, producing `Cannot read properties of undefined (reading '0')` and
  unmounting the drawer.
- The book-analytics API already returns `positive_pnl`, `negative_pnl`, and
  `net_pnl` for both books and both phases. No backend or ClickHouse query
  change is required.
- The overview currently summarizes Abook phase P&L only. The user-structure
  cards expose Bbook net P&L but do not present the three phase amounts as a
  clear, consistent metric group.

## Design

1. Replace the invalid de-extreme row loop with a `<template v-for>` wrapper;
   keep the row-level condition only on `v-if`.
2. Extend the overview phase summary component to calculate the same account
   level positive/loss/net split for Bbook and render a Bbook summary beside
   the existing Abook summary.
3. In `BookPerformance.vue`, render explicit `盈利金额`, `亏损金额`, and
   `净 P&L` rows for each book and phase using
   `analytics.pnl_structure[book].phase_summary[phase]`.
4. Add regression tests for the template structure, visible Bbook labels, and
   the existing backend phase fields. Use the existing frontend source
   contract tests because this project does not have a Vue component test
   runner.

## Data and Display Semantics

- `盈利金额` is the sum of positive account client-net-P&L values.
- `亏损金额` is the sum of negative account client-net-P&L values and remains
  negative in the display.
- `净 P&L = 盈利金额 + 亏损金额`.
- Both selection and validation periods use the same semantics for Abook and
  Bbook. Company profit remains a separate Bbook metric and is not substituted
  for customer P&L.

## Validation

- Source-contract tests must fail before the implementation and pass after it.
- Python test suite must pass, including book analytics and frontend contract
  tests.
- Frontend production build must regenerate `static/app.js` and complete
  successfully.
- In Chrome, clicking an Abook user must leave the drawer mounted after the
  detail response renders, and both overview and user-structure pages must
  show Bbook phase profit/loss/net amounts.
