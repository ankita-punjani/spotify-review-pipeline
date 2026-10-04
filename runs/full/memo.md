# Decision memo: next-quarter product priority

**Recommendation:** Put next quarter's effort into **billing/support**, starting with the free-tier limits that push people toward Premium:
- `billing.broad_paywall`: basic features now need Premium
- `billing.premium_only_controls`: rewind, repeat, shuffle and queue controls locked behind Premium
- `billing.free_song_choice`: free users can't pick or skip the songs they want

## Why billing

These three issues sit right next to each other in the ranking, at #3, #4 and #5:

- `billing.broad_paywall`: 20683 complaints [C009], priority score 56098 [C012]
- `billing.premium_only_controls`: 18694 complaints [C013], priority score 56084 [C016]
- `billing.free_song_choice`: 16048 complaints [C017], priority score 48254 [C020]

In these three issues, 3728, 4744 and 2838 reviewers said they were leaving or uninstalling. That's what they wrote, not proof that they actually left.

The bigger reason is the trend. Billing complaints went from 4.18% of all reviews in 2022-06..2022-11 to 13.94% in 2023-05..2023-10. Over the same months usability fell from 12.27% to 9.14%, and playback fell from 6.98% to 3.73%. Billing is the only large area that clearly got worse.

Typical reviews:
- "premium is required for everything, can't even rewind the track" (`705c0f44-00d6-4e67-8019-a9ce4aa0fee2`)
- "We can't hear some specific songs because it is in premium section" (`16cf6650-036c-4ce1-be06-c060276d141c`)

## What about the #1 issue?

`other.general` ranks first, with 68669 complaints [C001] and a priority score of 135595 [C004]. But these are reviews like "worst app" or "hate it" that don't name a specific problem, so there's nothing concrete for a team to fix. Their average severity is only 1.974617 [C003].

## Other options we looked at

**Usability.** Ads are the strongest alternative. `usability.ad_interruptions` is #2, with 36295 complaints [C005] and a priority score of 74151 [C008], more than any single billing issue. We'd look at ads next. Billing still comes first for two reasons:
- ad complaints are mostly mild annoyance (average severity 2.043009 [C007])
- usability's share of reviews is going down, not up

**Playback.** Fewer complaints, but more serious ones. `playback.app_crash_freeze` is #8 with 10266 complaints [C029]. `playback.wont_start` is #9 with 7945 complaints [C033] and an average severity of 3.579862 [C035]. Playback's share of reviews has roughly halved, so it doesn't look like it's getting worse. If it starts rising again, it should move up.

**Access.** Not being able to log in is serious. `access.general` has the highest average severity of the top-ranked issues, 3.918019 [C043], but it's only #13, with 4623 complaints [C041]. Its share went up a little, from 0.96% to 1.8%, so it's worth watching.

**Support.** Very small. `support.no_response` has 270 complaints [C045]. It doesn't change the decision.

## What to keep in mind

- **Reviews aren't a fair sample.** These are public app-store reviews, so the people who write them don't represent all users. We don't have money, plan or real cancellation data, so this says nothing about financial impact.
- **The labels come from a model.** A second, independent check on 1000 reviews agreed on the topic 0.852 of the time, and on topic, intent and severity together 0.742 of the time.
- **The most common mix-up is right on this memo's boundary.** It was between billing and usability, exactly the free-tier line this memo is about. Even so, moving a few thousand complaints from billing to usability wouldn't undo a jump from 4.18% to 13.94%.
- **The most severe billing reviews are less reliable.** Some of the most severe reviews filed under these billing issues are really about lost playlists or deleted accounts, not paywalls. Trust the overall volume of these issues more than their severe-complaint counts.
- **Coverage.** 660608 of 660622 reviews were classified. 14 were set aside: 13 empty reviews, and 1 that was just "very" repeated over and over. 159701 reviews have no app version.
- **Comparing the two time windows.** They have different numbers of reviews (175708 vs 301434), and the first and last months in the data are partial, so we compared full months only.

## What to check next quarter

- Re-run this same pipeline each month and watch whether the three billing issues keep growing.
- Count the people who say they'll leave in these three issues separately from the complaint totals.
- Re-check a sample of billing vs usability labels by hand, since that's where the model is least sure.
- Compare complaints by app version, using the reviews that have one.
