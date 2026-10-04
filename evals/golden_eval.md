# Golden-50 evaluation (human labels vs full-run predictions)

Run: `runs/full` · cases 50 · valid predictions 50 · human-marked ambiguous 16

| measure | strict (human primary label) | lenient (any label the human accepted) |
|---|---:|---:|
| topic agreement | 86% | 92% |
| intent agreement | 94% | 94% |
| severity agreement | 90% | 90% |
| all three agreement | 76% | 80% |

- Severity MAE: 0.12 vs primary, 0.12 vs closest accepted.
- Sentiment MAE 0.254; within ±0.3: 66%.
- Evidence quotes that are exact source substrings: 50/50.
- Entities: human 19, model 43, overlap 13; model entities not literally in the text: 0.
- needs_review as a predictor: {"flagged_and_wrong": 3, "flagged_and_right": 6, "unflagged_and_wrong": 7, "unflagged_and_right": 34, "wrong_means": "outside the human's accepted topic/intent/severity"}

## Topic confusion (rows = human, columns = model)

| human \ model | access | usability | playback | downloads | catalog | billing | support | other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| access |  |  | 1 |  |  |  |  |  |
| usability |  | 6 |  |  |  | 1 |  | 1 |
| playback |  |  | 3 |  |  | 1 |  |  |
| downloads |  |  |  | 1 |  |  |  |  |
| catalog |  |  |  |  | 6 |  |  | 1 |
| billing |  | 1 |  |  |  | 2 |  |  |
| other |  |  |  |  |  | 1 |  | 25 |

## Every disagreement (strict)

| # | review | human | model | accepted alternatives? | human note |
|---|---|---|---|---|---|
| 1 | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks truth. Spotify is do | catalog/complaint/1 | catalog/complaint/3 | no | religious-political rant, only product link is songs being banned |
| 2 | Ads were okay, but limited functionality..it's just too much | usability/complaint/3 | billing/complaint/3 | no | "limited functionality" is vague, possibly free-tier limits |
| 3 | Spotify is awesome and and very diverse :) | catalog/praise/1 | other/praise/1 | no | "diverse" = catalog |
| 4 | Duo Premium .... No ads at all! | usability/praise/1 | other/praise/1 | no | praising no ads, Premium mention alone isn't billing |
| 5 | Very good but wen I play my song it o ly plays a little bit then it stops I updated my phone and it worked but | playback/complaint/4 | playback/complaint/3 | no |  |
| 6 | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | usability/complaint/2 | usability/request/1 | no | Hindi, "please reduce ads, one after every song", also has "request" as intent c |
| 7 | Bheekhmangon | other/complaint/2 | other/unclear/1 | no | Hindi for "beggars", likely a jab at paywall |
| 8 | Unconditional love, Stoli Canales | other/praise/1 | other/unclear/1 | no | could be a name/signature |
| 9 | What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working. So I unstalled and | access/complaint/4 | playback/complaint/4 | no |  |
| 10 | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/1 | billing/unclear/1 | yes | ambiguous: also accept request / billing. Note: nonsense, maybe about a free tri |
| 11 | I gave one star because I can't give any less than that. the new update is sooooooo annoying like I can't even | playback/complaint/3 | billing/complaint/3 | yes | ambiguous: also accept billing / sev 4. Note: probably free-tier limits |
| 12 | Too expensive and the free version is pretty much unusable with constant ads... Every two or three songs.. For | billing/complaint/3 | usability/complaint/2 | no | ambiguous: also accept usability / cancellation. Note: "forget it" may mean leav |
