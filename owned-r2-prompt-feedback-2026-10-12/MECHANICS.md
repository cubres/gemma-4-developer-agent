# Prompt mechanics and a CPU reproduction

The owned command backend invokes Bash with `-c`. Bash replaces `PIPESTATUS` when another command executes. Capture the producer status immediately after the pipeline:

```bash
(printf 'original check fail\n'; exit 7) | tail -15
check_status=${PIPESTATUS[0]}
printf 'CHECK_EXIT=%s\n' "$check_status"
exit "$check_status"
```

Under `/bin/bash -c`, this harmless original control prints `CHECK_EXIT=7` and returns 7. It needs no repository task or model. Replacing the producer with `(printf 'original check pass\n'; exit 0)` returns 0. The appendix applies the same capture to the nearest real test command; the placeholder test path is not evidence that any test ran.

| Original bounded control | Observed exit | What it establishes |
|---|---:|---|
| Producer exits 0; capture immediately | 0 | Producer success survives the pipeline |
| Producer exits 7; capture immediately | 7 | Producer failure survives `tail` success |
| Producer exits 0; downstream exits 9; capture first status | 0 | First status describes the producer only |
| Producer exits 7; inspect pipeline exit without capture | 0 | A successful `tail` can hide producer failure |
| Producer exits 7; run `:` before capture | 0 | Another command destroys the original pipeline status |

All five controls ran with a two-second wall timeout per subprocess and a minimal `PATH`/`LC_ALL` environment. They exercise shell behavior only. The real model-free template check also preserved the literal `${PIPESTATUS[0]}` expression: it is not a valid template state identifier and was not substituted.

The unchanged contract uses the allowed 31B model alias for engineer and scout; 5 minutes, 100 charged calls, 160 turns, and a 90-second command timeout. The engineer declares `run_command`, `read_file`, `edit_file`, `write_file`, `get_status`, `submit_patch`, and the scout agent tool. Scout declares command and file reading; its read-only behavior is an instruction rather than an enforced capability restriction. Status, patch submission, and scout entry are free in charged-call accounting while still consuming time. Sampling remains in the readable builder source.

The archive has exactly six members, four YAML files and two Markdown prompts, with engineer and scout roles. Include targets, declarations and prompt templates compiled under the original allowed contracts. The five members outside the engineer prompt match the baseline bytes. The source-format builder checks the ZIP digest, size, member order and CRC without importing an organizer package.
