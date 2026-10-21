section: Repository hygiene
- **The Rails-assumption inventory sees Rails idioms named without the word Rails — `scripts/rails_assumptions.py`** (#2196 review).
  - **The new pattern.** `rails-idiom` covers `Current.*`, `perform` as code or `perform_later`/`perform_now`, `form_with`/`form_for`, the association macros and the controller callbacks. The English verb "perform" and the word "current" are not hits.
  - **The re-measure.** It finds 21 files, every one already classified (rails-stack, detector or reword), so no unclassified file. Setup-flow's section table loses the template row: it has no hit left.
  - **Proof.** The selftest has 4 new checks; the guard is 17 mutations, all caught.
