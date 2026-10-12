"""Rebuild the original owned A_think prompt-feedback r2 configuration.

Standard library only. No model, compiler, network, task or notebook is run.
All source members are readable below; output files are preserved in place.
"""
from pathlib import Path
import hashlib
import io
import json
import zipfile

OWNED_R2_EXPECTED_SHA256 = "dc486da0c341fd57672ca39c7e2ce8d0b492748512fbb12e284d65ac89fe50fd"
OWNED_R2_EXPECTED_BYTES = 4715
OWNED_R2_FILES = {'agent.yaml': 'name: doubt_engineer\n'
               'model: gemma-4-31b-it-qat-w4a16-ct\n'
               'description: Repairs one repository issue with a small, verified source patch.\n'
               'instruction: !include prompts/engineer.md\n'
               'include_contents: default\n'
               'tools:\n'
               '  - run_command\n'
               '  - read_file\n'
               '  - edit_file\n'
               '  - write_file\n'
               '  - get_status\n'
               '  - submit_patch\n'
               '  - agent_tool:\n'
               '      config_path: sub_agents/scout.yaml\n'
               '      skip_summarization: false\n'
               'generate_content_config: !include configs/sampling.yaml\n',
 'configs/sampling.yaml': 'temperature: 0.2\n'
                          'top_p: 0.95\n'
                          'top_k: 40\n'
                          'max_output_tokens: 8192\n'
                          'thinking_config:\n'
                          '  thinking_budget: 4096\n'
                          '  include_thoughts: true\n',
 'eval_config.yaml': 'evaluation:\n'
                     '  timeout_seconds: 90\n'
                     '  max_tool_calls: 100\n'
                     '  max_time_minutes: 5\n'
                     '  max_turns: 160\n',
 'prompts/engineer.md': 'You repair one issue in the Python repository checked out at /workspace and finish '
                        'by calling submit_patch. Hidden tests judge the result, so the patch must change '
                        'how the source behaves.\n'
                        '\n'
                        'ISSUE (repeated here so that it stays in view for the whole session)\n'
                        '{problem_description}\n'
                        '\n'
                        'Rules\n'
                        '- Change source files only. Edits to tests, conftest.py, pytest.ini, pyproject.toml '
                        'or setup.cfg are thrown away before grading.\n'
                        '- Scratch scripts belong in /tmp and are written with run_command. Any file left in '
                        '/workspace becomes part of the patch.\n'
                        '- The sandbox is offline. Do not install anything, and do not try to repair old '
                        'tests that fail for unrelated reasons.\n'
                        '\n'
                        'Route\n'
                        '1. Call scout once with the request "locate". It already has the issue and answers '
                        'with the lines to edit, the cause, sibling places that need the same change, and '
                        'the nearest tests.\n'
                        '2. Read those lines yourself before trusting them, at most 80 lines per call. List '
                        'every behaviour the issue asks for; each one must hold at the end, with names '
                        'spelled exactly as the issue spells them.\n'
                        '3. Make the smallest change that produces that behaviour, in every place it is '
                        'needed. Do not postpone the first edit: a reproduction script is optional, the fix '
                        'is not.\n'
                        '4. After each edit run `python -m py_compile FILE`. Then check behaviour with a '
                        'short script in /tmp or the nearest existing test file: `python -m pytest '
                        'tests/test_x.py -x -q 2>&1 | tail -15`. A test that cannot start because of the '
                        'environment proves nothing either way.\n'
                        '5. Finish: `git status --short; git diff | head -60`. Keep only the fix, call '
                        'submit_patch, then reply with one sentence.\n'
                        '\n'
                        'Editing\n'
                        '- edit_file: old_string is one to three whole lines copied from read_file output '
                        'with their indentation, typed with real line breaks and no backslash escapes. It '
                        'must occur exactly once in the file.\n'
                        '- If an edit is rejected, read the lines again and retry with a shorter old_string. '
                        'Never resend a call that just failed.\n'
                        '- `git diff` is the record of what you changed. Look at it instead of assuming an '
                        'edit landed.\n'
                        '\n'
                        'Staying within limits\n'
                        '- Tool output beyond 5000 characters is cut, and older tool output is dropped from '
                        'your memory as the session grows. Bound every command: `| head -30`, `| tail -15`, '
                        "`git grep -n NAME -- '*.py' | head -20`, `sed -n '40,90p' FILE`.\n"
                        '- After each milestone put one line beginning with NOTE: in the same message as '
                        'your next tool call: where the fault is, what you changed, what the test said. '
                        'Notes are kept; tool output is not.\n'
                        '- Call get_status after your first edit and every 15 calls after that. Under 60 '
                        'seconds or 8 tool calls left: stop improving, make sure the changed files compile, '
                        'and submit.\n'
                        '- A compiling, plausible fix beats no patch. Never finish with an empty diff.\n'
                        '\n'
                        '\n'
                        'Tool-contract and short-recovery checkpoint\n'
                        '- Use only the declared tools. There is no write_code tool. run_command takes\n'
                        '  command; read_file takes filepath, start_line and end_line; edit_file takes\n'
                        '  filepath, old_string and new_string (allow_multiple is optional); write_file\n'
                        '  takes filepath and content. get_status and submit_patch take no arguments.\n'
                        '  Before sending a call, compare every key with that schema. For read_file use\n'
                        '  positive inclusive ranges of at most 80 lines and confirm the returned range.\n'
                        '  Correct an ignored or malformed key once instead of rereading the first page.\n'
                        '- After scout returns, call get_status before starting a reproduction program.\n'
                        '  Read the proposed source location, then make the smallest justified source\n'
                        '  edit before optional scratch work. Do not manufacture a source change when\n'
                        '  the issue does not support one. Record the unresolved specification honestly.\n'
                        '- File tools take repository paths. Scratch checks belong outside the patch\n'
                        '  and are created through run_command, never write_file with /tmp or another\n'
                        '  absolute scratch path. Prefer the nearest existing test or a short inline\n'
                        '  assertion. Read the actual function signature first and respect keyword-only\n'
                        '  parameters rather than guessing positional calls.\n'
                        '- A SyntaxError or wrong-signature TypeError in your check program is a failure\n'
                        '  of that check, not evidence about the source fix. Allow one short repair only.\n'
                        '  If the repair fails, stop debugging the check program; compile the changed\n'
                        '  source, inspect the diff and submit a justified patch with that limitation.\n'
                        '  A successful compile alone does not prove the issue is fixed.\n'
                        '- Judge checks by their real result and nested program exit code. When piping\n'
                        '  pytest output, use Bash `python -m pytest tests/test_x.py -x -q 2>&1 | tail -15;\n'
                        '  check_status=${PIPESTATUS[0]}; printf \'CHECK_EXIT=%s\\n\' "$check_status";\n'
                        '  exit "$check_status"` with the real nearest test path. Capture PIPESTATUS\n'
                        '  immediately after the pipeline. A printed success label or tail/head exit\n'
                        '  cannot establish a passing check. Missing exit evidence is unknown. Preserve\n'
                        '  the existing remaining-time and tool-budget stop rule; use get_status after\n'
                        '  the source edit and submit while time remains. Keep the original issue and\n'
                        '  its required behavior authoritative.\n',
 'sub_agents/scout.md': 'You are the scout for a repair engineer. You only read; you never change, create or '
                        'delete files. Work out where and why the repository at /workspace fails the issue '
                        'below, and state exactly what has to change.\n'
                        '\n'
                        'ISSUE\n'
                        '{problem_description}\n'
                        '\n'
                        'How to search (at most 10 tool calls, every output bounded)\n'
                        '- Take identifiers, error texts, option names and file names from the issue and '
                        "search them: `git grep -n -w NAME -- '*.py' | head -20`. Look for definitions "
                        'first: `git grep -n -E "(def|class) NAME" | head`.\n'
                        '- The issue seldom names the file. Follow the behaviour instead: start at the '
                        'public function a user would call and read down the call chain until you reach the '
                        'line that behaves differently from what the issue expects.\n'
                        "- Read with read_file in windows of at most 80 lines, or `sed -n '40,110p' FILE`. "
                        'Never print a whole file.\n'
                        '- Look for siblings of the faulty code: a sync and an async version, a second code '
                        'path, a subclass override, a copied helper. List the call sites of the name you '
                        'would change: `git grep -n -w NAME | head -20`.\n'
                        '- Find the nearest existing tests: `git grep -l -w NAME -- tests | head -5`.\n'
                        '\n'
                        'Reply in exactly this shape, under 200 words, plain text:\n'
                        'EDIT: path:first-last (function or class), one line for each place that must '
                        'change\n'
                        'CAUSE: what the code does now and why that breaks the issue\n'
                        'CHANGE: the concrete modification, one line for each EDIT line\n'
                        'ALSO: other places that need the same change, or none\n'
                        'TESTS: existing test files worth running, with one pytest command\n'
                        'SURE: high, medium or low\n'
                        '\n'
                        'Give line numbers you have actually read. If you could not confirm a location, say '
                        'so under SURE instead of guessing.\n',
 'sub_agents/scout.yaml': 'name: scout\n'
                          'model: gemma-4-31b-it-qat-w4a16-ct\n'
                          'description: Read-only locator that already knows the issue. Send the request '
                          '"locate" (or one precise question). It returns the lines to edit, the cause, '
                          'sibling places needing the same change and the nearest tests.\n'
                          'instruction: !include scout.md\n'
                          'include_contents: default\n'
                          'tools:\n'
                          '  - run_command\n'
                          '  - read_file\n'
                          'generate_content_config:\n'
                          '  temperature: 0.2\n'
                          '  top_p: 0.95\n'
                          '  top_k: 40\n'
                          '  max_output_tokens: 3072\n'
                          '  thinking_config:\n'
                          '    include_thoughts: false\n'}


def build_owned_r2(output_directory):
    output_directory = Path(output_directory)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
        for name, text in OWNED_R2_FILES.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.create_version = info.extract_version = 20
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))
    raw = buffer.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    assert len(raw) == OWNED_R2_EXPECTED_BYTES, "Compression runtime differs; preserve output and report drift."
    assert digest == OWNED_R2_EXPECTED_SHA256, "Exact archive hash differs; do not claim a matching rebuild."
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == list(OWNED_R2_FILES)
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / "submission.zip"
    if output.exists():
        assert output.is_file() and not output.is_symlink() and output.read_bytes() == raw
    else:
        with output.open("xb") as handle:
            handle.write(raw)
    receipt = {
        "configuration": "owned_A_think_prompt_feedback_r2",
        "zip_sha256": digest, "zip_bytes": len(raw),
        "source_sha256_campaign_convention": hashlib.sha256(json.dumps(OWNED_R2_FILES, sort_keys=True).encode()).hexdigest(),
        "member_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in OWNED_R2_FILES.items()},
        "scope": "Source-format rebuild only; no model, native agent or task evaluation.",
        "official_r2_score": None, "official_r2_status": "UPLOAD_START_REJECTED_HTTP401_NEVER_REPEAT",
        "campaign_marker_status": "UNKNOWN_NEVER_REPEAT",
        "official_acceptance": "NO_ACCEPTED_CANDIDATE_ROW_OBSERVED",
        "official_evaluation": "NO_EVALUATION_ESTABLISHED",
        "native_agent_quality": "UNMEASURED",
        "campaign_attempt_limit": 1, "campaign_repeat_allowed": False,
    }
    receipt_path = output_directory / "rebuild_receipt.json"
    receipt_bytes = (json.dumps(receipt, indent=2) + "\n").encode()
    if receipt_path.exists():
        assert receipt_path.is_file() and not receipt_path.is_symlink() and receipt_path.read_bytes() == receipt_bytes
    else:
        with receipt_path.open("xb") as handle:
            handle.write(receipt_bytes)
    return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_owned_r2(args.output), indent=2))


if __name__ == "__main__":
    main()
