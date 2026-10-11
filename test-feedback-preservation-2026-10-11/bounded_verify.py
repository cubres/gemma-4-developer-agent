"""Build a bounded Bash command that preserves the producer's exit status.

Original stdlib-only helper. It builds text; it never executes the command.
The caller supplies a trusted argument vector and keeps its existing timeout.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence


def bounded_command(
    argv: Sequence[str], *, line_limit: int = 15, byte_limit: int = 3000
) -> str:
    """Return a run_command-compatible command, with an explicit status trailer.

    Output is the last line_limit lines, cropped to the last byte_limit bytes,
    followed by a status trailer. The limit is output size, not producer memory
    or runtime. When either tail stage fails, return 125 (unverified output).
    Otherwise return the producer's own shell exit status, including failures.
    """
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or not argv:
        raise ValueError("argv must be a nonempty argument sequence")
    if any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise ValueError("each argument must be a string without NUL")
    if not argv[0]:
        raise ValueError("the executable name must be nonempty")
    if type(line_limit) is not int or not 1 <= line_limit <= 200:
        raise ValueError("line_limit must be an integer from 1 through 200")
    if type(byte_limit) is not int or not 1 <= byte_limit <= 3500:
        raise ValueError("byte_limit must be an integer from 1 through 3500")
    producer = " ".join(shlex.quote(item) for item in argv)
    script = "\n".join(
        [
            "set +e",
            "set +o pipefail",
            f"{producer} 2>&1 | tail -n {line_limit} | tail -c {byte_limit}",
            'verify_status=("${PIPESTATUS[@]}")',
            "printf '\\nVERIFY_PRODUCER_EXIT=%s VERIFY_TAIL_EXIT=%s,%s\\n' "
            '"${verify_status[0]}" "${verify_status[1]}" "${verify_status[2]}"',
            'if [ "${verify_status[1]}" -ne 0 ] || '
            '[ "${verify_status[2]}" -ne 0 ]; then exit 125; fi',
            'exit "${verify_status[0]}"',
        ]
    )
    return "/bin/bash -c " + shlex.quote(script)
