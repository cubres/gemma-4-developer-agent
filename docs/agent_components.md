# Inspect source and recognize repeated tool responses

The repository contains three original, standard-library Python components. They are independently useful without a model server. Their 91 synthetic tests check mechanics, containment, serialization, and tool-response handling. No solve-rate improvement is established by those tests.

From the repository root, with Python 3.12:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

For the import examples below, start Python from the repository root with `PYTHONPATH=src python`, or run your own script with `PYTHONPATH=src python your_script.py`.

## Bounded source locator

```python
from pathlib import Path
from bounded_ast_locator import locate

root = Path("/absolute/path/to/your/source").resolve(strict=True)
report = locate(root, "dispatch parse_result")
print(report["status"], report["locations"], report["edges"])
```

The locator parses Python syntax without executing repository source. It returns at most six definitions and 24 directed static call hints. Each location keeps `filepath`, `start_line`, and `end_line` separate. Name, path, and nearby documentation tokens guide retrieval; this is lexical retrieval over syntax, rather than semantic model inference.

Traversal has limits on files, directory entries, bytes, syntax nodes, and elapsed time. Hidden directories, test directories, environments, and symlinks are excluded. A global limit returns `LIMIT` with no partial definition selection. Syntax and encoding gaps are reported. Static call hints explicitly retain uncertainty around imports, rebinding, dynamic dispatch, and inheritance.

The root must already be an absolute canonical directory. Descriptor-based traversal requires POSIX support for `O_NOFOLLOW` and `O_DIRECTORY`. This component is intended for macOS/Linux; Windows behavior is unverified.

## Skill script wrapper

`src/locator_skill.py` fixes the repository root to `/workspace`, accepts a scalar query and scalar limit arguments, and emits one JSON line of at most 4,500 UTF-8 bytes. For an environment with that workspace:

```bash
python src/locator_skill.py --query 'dispatch parse_result'
```

Copy `locator_skill.py` and `bounded_ast_locator.py` together into an owned skill's `scripts/` directory. The wrapper verifies the exact sibling core hash before loading it and does not resolve that dependency from the current working directory or Python import cache. Updating the core requires a deliberate wrapper hash update and revalidation.

Output compaction records omitted locations, edges, excerpts, and gaps. A successful scan returns exit code 0; a traversal limit returns 1; handled input or resource errors return 2. Nonzero results retain structured JSON. Actual compiler integration and model-facing execution need their own validation.

## Repeat-response controller

```python
from repeat_recovery import RepeatRecoveryController

controller = RepeatRecoveryController()
for _ in range(3):
    decision = controller.observe(
        actor="root", tool="run_command",
        arguments={"command": "rg missing_symbol src"},
        observation={"exit_code": 1, "stdout": "", "stderr": ""},
    )
print(decision.event, decision.feedback)
```

One instance belongs to one task/session. It tracks actor streams separately and recognizes repeated calls with stable observations. Default feedback occurs at 3, 6, 12, and subsequent doubling intervals. Budget-only metadata and its own feedback do not hide repeated behavior; substantive payload changes do.

An empty `grep`/`rg`/`git grep` exit-1 response can mean absence. `find` exit 1 remains an error. Charged tool calls stay unknown until authoritative status or an explicit counter supplies them; raw responses are counted separately. A captured nonempty patch permits a completion handoff but does not prove correctness.

The controller is a development utility. The competition compiler's supported configuration does not expose arbitrary callbacks, so this file is not a drop-in callback registration or a scored agent submission.

All three components and their tests carry the MIT license in their source files.
