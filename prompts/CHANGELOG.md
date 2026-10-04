# Prompt changelog

All changes are driven by development data (smoke_50, checkpoint_500, analysis_10000). The golden 50 are never used for tuning.

- **enrich_v1** (2026-10-03): initial prompt from GRADING_CONTRACT.md definitions plus illustrative (non-dataset) examples.
- **enrich_v2** (2026-10-03): after reading 40 random complaint labels from checkpoint_500:
  - praise + wished-for feature with no failure → `request` (v1 labelled "enjoyed the blend feature… being able to rename" as complaint);
  - lyrics missing/not loading → `catalog` per the contract's "lyrics availability" (v1 sent "lyrics couldn't load" to playback).
- **enrich_v3** (2026-10-03): adds the `sub` field — one frozen subtopic from `taxonomy/subtopics_v1.json` (40 issue IDs) — so issue membership is assigned during the single full run; no label definitions changed. Code also gained fuzzy quote repair (typo-corrected quotes are mapped back to the exact source span) and a final-attempt full-text quote fallback for reviews <= 600 chars, both flagged in record notes.
- **memo_v2** (2026-10-04): after the dev10k rehearsal memo — require the memo to state why generic `other.*` issues are not an actionable area, treat billing+support as one area as the question frames it, and use issue names alongside IDs.
- **name_v1** (2026-10-04): new group-role task — name + summarize each top issue from 12 seeded member quotes and flag misfits (membership unchanged).
