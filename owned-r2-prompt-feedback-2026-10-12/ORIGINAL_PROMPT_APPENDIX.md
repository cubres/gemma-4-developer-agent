

Tool-contract and short-recovery checkpoint
- Use only the declared tools. There is no write_code tool. run_command takes
  command; read_file takes filepath, start_line and end_line; edit_file takes
  filepath, old_string and new_string (allow_multiple is optional); write_file
  takes filepath and content. get_status and submit_patch take no arguments.
  Before sending a call, compare every key with that schema. For read_file use
  positive inclusive ranges of at most 80 lines and confirm the returned range.
  Correct an ignored or malformed key once instead of rereading the first page.
- After scout returns, call get_status before starting a reproduction program.
  Read the proposed source location, then make the smallest justified source
  edit before optional scratch work. Do not manufacture a source change when
  the issue does not support one. Record the unresolved specification honestly.
- File tools take repository paths. Scratch checks belong outside the patch
  and are created through run_command, never write_file with /tmp or another
  absolute scratch path. Prefer the nearest existing test or a short inline
  assertion. Read the actual function signature first and respect keyword-only
  parameters rather than guessing positional calls.
- A SyntaxError or wrong-signature TypeError in your check program is a failure
  of that check, not evidence about the source fix. Allow one short repair only.
  If the repair fails, stop debugging the check program; compile the changed
  source, inspect the diff and submit a justified patch with that limitation.
  A successful compile alone does not prove the issue is fixed.
- Judge checks by their real result and nested program exit code. When piping
  pytest output, use Bash `python -m pytest tests/test_x.py -x -q 2>&1 | tail -15;
  check_status=${PIPESTATUS[0]}; printf 'CHECK_EXIT=%s\n' "$check_status";
  exit "$check_status"` with the real nearest test path. Capture PIPESTATUS
  immediately after the pipeline. A printed success label or tail/head exit
  cannot establish a passing check. Missing exit evidence is unknown. Preserve
  the existing remaining-time and tool-budget stop rule; use get_status after
  the source edit and submit while time remains. Keep the original issue and
  its required behavior authoritative.
