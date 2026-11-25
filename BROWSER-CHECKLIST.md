# Browser smoke test (not yet executed in this environment)

1. Open `/` at 1440px: seven day cards across four wider columns; current day highlighted, no hour grid or scheduling fields.
2. Enter two titles in one day. Press Enter / Add task. No navigation is required with JS enabled.
3. Complete and reopen each checkbox. Verify daily/week counts; refresh and verify persistence.
4. Delete from a day card. Follow View or restore task; restore it and verify the board.
5. Open a daily title, edit description, notes, priority and date. Reload and navigate to that week.
6. Use previous/next week and Today. Check a long title and Persian text wrap without overflow.
7. Create a long-term task, add two checklist steps and comments; edit/delete a comment.
8. Link a daily task, complete it, confirm parent status is unchanged. Complete the parent,
   verify it is hidden from active/dashboard views and retained in Completed. Reopen it.
9. Check Skills CRUD, Activities CRUD, Insights charts and navigation still work.
10. At 390px: days stack, forms and navigation are usable, no page-wide horizontal overflow.
11. With keyboard: follow focus order, activate task links, checkbox, add/delete, week navigation.
12. Disable JavaScript: add and toggle using ordinary forms / Save buttons, then verify persistence.
13. Simulate a failed write: the error is visible, checkbox reverts, quick-add text is retained.
14. Inspect the browser console for errors and confirm CDN resources load.

15. Verify top statistics, per-skill stacked minute tooltips, and unchanged doughnut.
16. Confirm each skill appears once per day; deleting a default then refreshing does not restore it.
17. Open task permanent deletion, cancel, then confirm on a disposable task. Check all linked children are removed.
