# Decision memo: next-quarter product priority

**Recommendation** — Prioritize **billing/support**, beginning with clearer, more consistent free listening and playback controls: `billing.free_song_choice` (Free Song Choice Limits) and `billing.premium_only_controls` (Premium-Locked Playback Controls). Also review `billing.broad_paywall` (Basic Features Behind Premium) to identify whether it reflects the same underlying confusion or a distinct issue.

## Evidence — why this area

Billing is the strongest actionable cluster among the four candidate areas: it accounts for 11 complaints, severity_sum 32, and share_of_ranked_complaints_pct 22.000000. The trend is also notable: billing’s share is 8.7 in 2022-07..2022-12 (2 ranked complaints among 23 reviews) and 16.67 in 2023-05..2023-10 (8 among 48). These are review shares, not measures of overall customer experience.

Specific billing issues recur near the top of the ranking. Free Song Choice Limits, `billing.free_song_choice`, ranks 3, with 4 complaints [C009] and priority_score 12 [C012]. Premium-Locked Playback Controls, `billing.premium_only_controls`, ranks 4, with 4 complaints [C013] and priority_score 12 [C016]. Basic Features Behind Premium, `billing.broad_paywall`, ranks 5, with 3 complaints [C017] and priority_score 8 [C020]. The billing topic has 2 cancellation-intent reviews; this means reviewers said they would leave, not that they did. The reviews illustrate the concern: free song choice ( `a3605554-5c3a-441d-836e-e9fdea83eb2e`, `d146397f-4a94-4980-be00-ae9212eca3a7`) and premium-locked controls (`88439ec2-7c49-4c57-bedb-c5e098692aff`).

`other.general` (General App Dislike) ranks 1, with 8 complaints [C001] and priority_score 16 [C004], but it is generic dislike without a specific product problem: it is not an actionable product area on its own. `other.update_regression` is similarly nonspecific absent a concrete failure to investigate.

## Alternatives considered

**Usability:** Frequent and Disruptive Ads, `usability.ad_interruptions`, ranks 2, with 7 complaints [C005] and priority_score 14 [C008]. Usability has 11 complaints and severity_sum 24 at topic level. Its share moved from 13.04 in the early window to 8.33 in the late window. Ads merit monitoring, and review `035213ba-b1b9-411c-b028-70296e5f0e73` expresses cancellation intent, but the billing cluster is larger in the late-window share and contains multiple specific high-ranked issues.

**Playback:** Playback has 6 complaints and severity_sum 21. App Crashes or Won’t Load, `playback.app_crash_freeze`, ranks 6, with 2 complaints [C021], mean_severity 4.000000 [C023], and priority_score 8 [C024]. Playback Won’t Start, `playback.wont_start`, ranks 7, with 2 complaints [C025] and priority_score 7 [C028]. Their severity makes them important reliability checks, but the complaint volume and late-window share (4.17) are below billing’s.

**Access:** Access has 2 complaints and severity_sum 8. General Account Access, `access.general`, ranks 12, with 1 complaint [C041] and priority_score 4 [C044]. Its late-window share is 2.08. The individual report is serious, but this evidence is too sparse to put access ahead of the billing cluster.

## Risks and limitations

Classification coverage is 100 completed out of 100 source rows, with 0 quarantined; 18 rows lack app-version information. Verification used a sample of 20: all-three agreement is 0.9, topic agreement 0.95, and severity MAE 0.05. Public reviews are self-selected and cannot establish prevalence or business impact. The trend compares 2022-07..2022-12 with 2023-05..2023-10; intervening periods are not shown, and partial first/last months limit interpretation.

## What to measure next quarter

- Re-run this classification pipeline and compare billing issue counts, severity, and cancellation-intent reviews.
- Track the free-song-choice and premium-controls issues separately, with evidence review IDs for audit.
- Compare topic shares using denominators and comparable periods; retain quarantine and app-version coverage reporting.
- Recheck label agreement on a fresh verification sample, especially for issue assignment and intent.