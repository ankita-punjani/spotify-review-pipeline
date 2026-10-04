# Decision memo: next-quarter product priority

**Recommendation** — Prioritize **billing/support**, starting with clearer free-experience boundaries for `billing.broad_paywall` (Basic Features Require Premium), `billing.premium_only_controls` (Playback Controls Behind Premium), and `billing.free_song_choice` (Free Song Choice and Skips). Validate these labels against review text as part of the work, since the evidence captures expressed complaints rather than confirmed product defects.

## Evidence — why this area

Billing combines substantial complaint volume with the clearest adverse trend among the candidate areas. It represents 63405 complaints and 21.662629% of ranked complaints, with topic mean severity 2.874474. Its share of reviews rises from 4.18% in 2022-06..2022-11 to 13.94% in 2023-05..2023-10. The windows have different denominators—175708 and 301434 reviews—so this is a signal to investigate, not an explanation of why complaints changed.

The three billing issues rank consecutively: `billing.broad_paywall` is rank 3, with 20683 complaints [C009] and priority score 56098 [C012]; `billing.premium_only_controls` is rank 4, with 18694 complaints [C013] and priority score 56084 [C016]; `billing.free_song_choice` is rank 5, with 16048 complaints [C017] and priority score 48254 [C020]. Reviewers expressed cancellation intent in 3728, 4744, and 2838 cases respectively; these are statements of intent, not observed departures. Representative evidence includes review `705c0f44-00d6-4e67-8019-a9ce4aa0fee2` for controls, `16cf6650-036c-4ce1-be06-c060276d141c` for song choice, and `aba61ee9-9e2b-4444-b84f-cb31b729d163` for broad paywalls.

The top-ranked issue, `other.general` (General App Dislike), is not an actionable product area on its own: it does not identify a specific product problem. It has 68669 complaints [C001] and priority score 135595 [C004], but mean severity is 1.974617 [C003]. It should not displace specific, rising billing concerns.

## Alternatives considered

**Usability.** The topic totals 72486 complaints, but its share falls from 12.27% to 9.14% across the supplied windows. `usability.ad_interruptions` (Frequent Listening Ads) ranks 2, with 36295 complaints [C005] and priority score 74151 [C008], and remains an important follow-up. `usability.queue_shuffle` (Unexpected Queue and Shuffle) ranks 6, with 13914 complaints [C021] and priority score 41465 [C024]. The high ranking of the ads issue merits monitoring, but the topic trend favors billing as the next-quarter focus.

**Playback.** Playback has mean severity 3.189749, the highest among these candidate topics, but its share falls from 6.98% to 3.73%. `playback.app_crash_freeze` (App Freezing, Crashing, or Failing to Load) ranks 8, with 10266 complaints [C029] and priority score 33647 [C032]. `playback.wont_start` (Playback Won’t Start) has mean severity 3.579862 [C035] but ranks 9, with 7945 complaints [C033] and priority score 28442 [C036]. Reconsider playback if its share or issue ranking rises in comparable periods.

**Access.** `access.general` (Unable to Sign In) has mean severity 3.918019 [C043], but ranks 13, with 4623 complaints [C041] and priority score 18113 [C044]. Its share rises from 0.96% to 1.8%; monitor the increase, while recognizing its lower current volume than the leading billing issues.

## Risks and limitations

Classification completed for 660608 of 660622 source rows; 14 were quarantined, including 13 empty-text quarantines. Independent verification on a sample of 1000 found all-three agreement of 0.742, topic agreement of 0.852, and severity MAE of 0.131. Reviews are self-selected public feedback, not representative customer research. App version is missing for 159701 rows. Trend windows have different denominators and partial first/last months. No observed departure or business-outcome data are available; cancellation counts are expressed intent only.

## What to measure next quarter

- Re-run the same classification and ranking; track billing issue counts, severity, cancellation statements, and topic share with comparable denominators.
- Independently re-label a sample of billing reviews and report agreement and quarantine counts.
- Compare issue patterns by app version where available, while reporting missing-version coverage.
- Audit representative reviews for the leading issues to confirm each identifies a specific product problem.