# Gemma progress: qualify the evaluation before choosing the agent

The official `prvsiyan` account snapshot at 19:11 UTC on 11 October 2026 separates the current best from an accepted entry whose row reports neither status nor score.

| Official evidence | Exact row | State |
|---|---:|---|
| Best completed result, A_think | 56949760 | COMPLETE — **0.12** |
| Most recent accepted entry, D v4 | 57039340 | UNKNOWN — score absent |

Row 57039340 omits both status and score, so its evidence state is **UNKNOWN**, rather than a reported PENDING status. Its agent strategy cannot be promoted on acceptance alone. The [competition submissions page](https://www.kaggle.com/competitions/gemma-4-developer-agent/submissions) is the source for completed official results.

The immediate finding concerns evaluation health. A caught task exception can still return a result object, and a successful wrapper exit does not prove that the planned tests executed. The standalone gate checks declarations; the linked receipt adapter binds retained XML bytes and native executed-test evidence into that gate. Together they form a receipt pipeline. That pipeline checks the complete planned denominator, explicit task errors, final executed-test exit and retained evidence through the original verification chain. A genuinely executed failing test is an unresolved result; infrastructure failure and missing evidence remain separate outcomes.

Time also needs the right origin. Model startup, environment preparation, the agent's problem-solving session and patch extraction occupy different parts of the wall clock. The prepared entry-bootstrap successor binds startup to the notebook's original entry clock and preserves the reviewed agent policy. The preparation state was recorded separately when drafting at **19:44 UTC**: its static review was retained at **19:24:59 UTC**, and it had not been launched. The earlier 19:11 account snapshot establishes only the official rows above; it does not attest this later preparation state. That is preparation for a measured native screen, not evidence of agent quality or runtime safety.

The next comparison must first return authentic task-complete receipts under that clock contract. Only then can a single strategy factor be compared with the scored control using the same task plan and serving conditions, retaining errors and timeouts in the denominator. A partial healthy screen cannot stand in for a complete evaluation or a hidden leaderboard result.

To reuse the work, start with the original [receipt gate](https://github.com/cubres/gemma-4-developer-agent/tree/764878bd6d214ef8aedea18a3027793bb9b65273/native-receipt-gate-2026-10-11) and [entry/clock join tools](https://github.com/cubres/gemma-4-developer-agent/tree/22a5acc9fc8c65388215893afa3777b3ab6788d2/native-entry-clock-join-2026-10-11). Their invented controls help test a receipt pipeline without running a model or organizer task. The [illustrated notebook companion](https://github.com/cubres/gemma-4-developer-agent/blob/5cfa5190c4b4ade6d463297f3f2e7900f0265a15/notebook-companion-2026-10-11-r1/COMPANION.md) gives a small runnable packaging example. Organizer interfaces, model assets and upstream agent components retain the campaign's existing attribution and their separate terms; these original tools confer no rights to redistribute them.
