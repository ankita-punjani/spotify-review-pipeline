# Decision memo: next-quarter product priority

**Recommendation** — Put next-quarter effort into **billing**, starting with `billing.broad_paywall`, `billing.premium_only_controls`, and `billing.free_song_choice`. The billing topic is growing in comparable review periods, and its leading issues combine high ranking positions with more expressed cancellation intent than usability.

## Evidence — why this area

Billing accounts for 996 complaints, severity sum 2841, mean severity 2.852410, and 198 cancellations. Its share of ranked complaints is 22.157953%. The trend strengthens the case: billing rises from 4.15% in 2022-06..2022-11 to 15.07% in 2023-05..2023-10; the corresponding all-review denominators are 2649 and 4525.

The issue ranking puts `billing.broad_paywall` at rank 3, with 347 complaints [C009], mean severity 2.746398 [C011], and priority score 953 [C012]. `billing.premium_only_controls` is rank 4, with 274 complaints [C013], mean severity 3.003650 [C015], and priority score 823 [C016]. `billing.free_song_choice` is rank 5, with 239 complaints [C017], mean severity 3.008368 [C019], and priority score 719 [C020]. Reviewers describe broad limits on song playback in `28c5e28e-0985-4e3a-acba-4f827124560d`, restricted controls in `e85607c3-a8b4-4a61-a548-a58b17b0eae1`, and inability to select a song in `3257da13-8a76-45ae-8acf-3fe83dfdcd5e`. The ranking’s cancellation counts are 68, 81, and 38 respectively; these are statements of intent to leave, not observed departures.

## Alternatives considered

**Usability** has the largest candidate-topic complaint count at 1161, but a lower mean severity of 2.458226 and 115 cancellations. Its share falls from 12.23% to 9.48% across the comparable periods. `usability.ad_interruptions` ranks 2, with 582 complaints [C005] and priority score 1191 [C008], so it remains a substantial issue; its cancellation count is 53. I would shift priority if the billing trend proved temporary or usability’s issue-level trend turned upward.

**Playback** has 554 complaints and 49 cancellations, with mean severity 3.207581 and 139 severity-4-plus complaints. That severity signal merits monitoring, especially for `playback.app_crash_freeze` (rank 8; 156 complaints [C029], priority score 512 [C032]) and `playback.wont_start` (rank 9; 123 complaints [C033], priority score 440 [C036]). However, playback’s share declines from 6.72% to 4.22% across the comparable periods. A confirmed rise in these failures would change the tradeoff.

**Access and support** are lower-volume alternatives. Access has 141 complaints and 7 cancellations, though its mean severity is 3.872340 and its share rises from 1.02% to 1.64%. `access.general` is rank 15, with 59 complaints [C041] and priority score 230 [C044]; validate whether its high-severity reports are concentrated before moving it ahead. Support has 4 complaints and 2 cancellations, too little volume here to justify leading next-quarter effort.

## Risks and limitations

Classification covered 10000 of 10000 source rows, with 0 quarantined and 0 empty-text quarantines; 1552 rows used exact-text cache reuse. In verification, the sample was 300; topic agreement was 0.8633, severity agreement 0.89, and all-three agreement 0.7567 (severity_mae 0.1233). These are useful but imperfect labels. Public reviews are self-selected and express intent, not representative usage or observed cancellation behavior. App version is missing for 2447 rows. The trend windows are separated, and the first/last months are partial. No churn data are available; do not treat expressed cancellation intent as an outcome.

## What to measure next quarter

- Re-run the same classification and ranking pipeline; compare billing complaint counts, severity, and ranking positions with this baseline.
- Track billing cancellation-intent counts separately from complaints, and keep them labeled as expressed intent.
- Recheck topic and severity agreement on a fresh verification sample; inspect disagreements before interpreting small shifts.
- Report comparable-period shares with review denominators and app-version completeness, flagging partial months and quarantines.