# Decision memo: next-quarter product priority

**Recommendation** — Put next-quarter effort into **billing/support**, led by clearer and more consistent free-experience limits. Start with `billing.premium_only_controls` (Playback Controls Behind Premium), `billing.free_song_choice` (Free Song Choice and Skips), and `billing.broad_paywall` (Basic Features Require Premium); validate the billing labels before treating every classified complaint as a confirmed product defect.

## Evidence — why this area

Billing has the strongest combination of scale, severity, and worsening share among the four candidate areas. It accounts for 63405 complaints and a 21.662629 share of ranked complaints; its topic mean severity is 2.874474. In the comparable trend windows, billing rises from 4.18% of reviews in 2022-06..2022-11 to 13.94% in 2023-05..2023-10. The denominators differ—175708 and 301434 reviews—so the movement is a signal to investigate, not a causal conclusion.

Three billing issues lead the actionable ranking: `billing.broad_paywall` is rank 3, with 20683 complaints [C009] and priority score 56098 [C012]; `billing.premium_only_controls` is rank 4, with 18694 complaints [C013] and priority score 56084 [C016]; `billing.free_song_choice` is rank 5, with 16048 complaints [C017] and priority score 48254 [C020]. Reviewers expressed cancellation intent in 3728, 4744, and 2838 cases respectively. These are statements of intent, not observed departures. The evidence illustrates perceived limits: `billing.premium_only_controls` review `705c0f44-00d6-4e67-8019-a9ce4aa0fee2`; `billing.free_song_choice` review `16cf6650-036c-4ce1-be06-c060276d141c`; and `billing.broad_paywall` review `aba61ee9-9e2b-4444-b84f-cb31b729d163`. Some examples may be misclassified, which is why label validation belongs in the work.

The rank-1 `other.general` issue is not an actionable product area on its own: “General App Dislike” does not identify a specific fix. It has 68669 complaints [C001] and priority score 135595 [C004], but low mean severity 1.974617 [C003]. Its rank should not outweigh the more specific billing evidence.

## Alternatives considered

**Usability.** This area has the largest candidate-topic volume, at 72486 complaints, but its share falls from 12.27% to 9.14% across the supplied windows. `usability.ad_interruptions` is rank 2, with 36295 complaints [C005] and priority score 74151 [C008]; it merits ongoing attention, but the trend does not support choosing it over rising billing concerns. `usability.queue_shuffle` is rank 6, with 13914 complaints [C021] and priority score 41465 [C024].

**Playback.** Playback has the highest candidate-topic mean severity, 3.189749, and remains a credible alternative. However, its share falls from 6.98% to 3.73%. Its highest-ranked issue, `playback.app_crash_freeze`, is rank 8, with 10266 complaints [C029] and priority score 33647 [C032]. `playback.wont_start` is more severe at 3.579862 [C035], but rank 9, with 7945 complaints [C033] and priority score 28442 [C036].

**Access.** `access.general` has high mean severity, 3.918019 [C043], but is rank 13, with 4623 complaints [C041] and priority score 18113 [C044]. Its share rises from 0.96% to 1.8%; monitor it, but its volume is below the leading billing issues.

## Risks and limitations

Classification completed for 660608 of 660622 source rows; 14 were quarantined, including 13 empty-text quarantines. Verification on a sample of 1000 found all-three agreement of 0.742 and topic agreement of 0.852; severity MAE was 0.131. Reviews are self-selected public feedback, not representative customer research. App version is missing for 159701 rows. The trend windows have different denominators and partial first/last months. There is no revenue or churn data; cancellation counts are expressed intent only, not causal effects or observed outcomes.

## What to measure next quarter

- Re-run the same classification and ranking; track billing issue counts, severity, cancellation statements, and topic share alongside comparable denominators.
- Independently re-label a sample of billing reviews, especially broad-paywall examples, and report agreement and quarantine counts.
- Compare issue trends by app version where available, while reporting missing-version coverage.
- Review representative evidence for each leading issue to confirm that the classified complaint names a specific product problem.