# Notebook execution map

Find a notebook's configuration assignments and compute-budget flags before choosing an experiment. This small command reads one file and emits JSON. It never imports or executes notebook code and never edits the input. It uses only the Python standard library.

This is a reader utility for any of the five campaigns in these repositories; it is published once here to avoid maintaining multiple copies.

## Run it

Use Python 3.10 or newer. From the repository root:

```sh
python3 -B tools/notebook-execution-map/2026-10-05/notebook_execution_map.py /absolute/path/to/notebook.ipynb
```

The report goes to standard output. It includes a SHA-256 of the complete input when it could be read within the size limit, code-cell counts, assignment locations, literal/dynamic classifications, and budget categories. Cell indices start at zero; code line numbers start at one. The command makes no network requests or output files. It requires a regular file.

The observed development environment is POSIX/macOS, where `O_NOFOLLOW` is available. When this flag exists, the open call refuses a symbolic link in the final path component only; symbolic links in parent directories can still be followed. On platforms without that flag, the code falls back to zero, so final-component symbolic-link refusal is not guaranteed. That fallback has not been certified. The existing filesystem-boundary test uses mocks; it does not establish live symbolic-link rejection on any platform.

Exit code `0` means a map was produced; check `status` for `MAPPED` or `PARTIAL`. Exit code `2` means `INVALID_INPUT` or an invalid command invocation. A file that cannot be read or is rejected before reading has a null `source_sha256`.

## What the map means

Only uppercase module bindings and bindings inside `CFG`, `Config`, or `Configuration` classes are listed. Function bodies and other class bodies are excluded. Repeated assignments remain separate; assignments inside control-flow blocks are marked conditional. No final effective configuration is inferred.

For example:

```python
# RUN_TEST = True             # ignored comment
RUN_TEST = False              # literal boolean
TIMEOUT = 30                  # literal number
MAX_SECONDS = 5 * 60          # dynamic BinOp; arithmetic is not evaluated
DEVICE = choose_device()      # dynamic Call; the call is never executed
```

Budget categories are inferred from names such as `RUN_`, `TIMEOUT`, `BATCH`, and `SEED`. They do not establish real runtime, quota cost, hardware compatibility, or which code will execute. String and compound literal values are omitted. Only direct scalar boolean constants and finite numeric constants can be displayed; other literal forms are classified without displaying their values.

Python magics and other non-Python cell syntax produce `PARTIAL`. An unparseable cell contributes to the code-cell count but has no assignments extracted; diagnostics give its cell index and, when available, line number. Notebook outputs, metadata, attachments, and embedded script strings are not inspected for configuration. Consequently a notebook that writes a training script from a string can contain important controls outside this map.

## Input limits

| Limit | Value |
|---|---:|
| File bytes | 2 MiB |
| Cells | 256 |
| Code characters across all cells | 1 MiB |
| Code characters in one cell | 256 KiB |
| AST nodes per parsed cell | 20,000 |
| Reported assignments | 512 |

Input must be UTF-8; a UTF-8 BOM is accepted. Oversized input, invalid encoding, malformed JSON, and invalid cell structures return a bounded error code without printing source text. Limits are hard refusals rather than silent truncation.

## Validation

The exact source and tests in this directory passed 15 synthetic checks during development on 5 October 2026. The unittest run reported 0.011 seconds; the surrounding runner measured 0.056885 seconds elapsed and 0.047679 CPU seconds. These are measurements of the synthetic checks, not notebook runtime estimates. No actual notebook was inspected to obtain them, and no separate persisted measurement receipt was created.

The checks cover ignored comments, literal versus dynamic expressions, configuration scopes, conditional and repeated assignments, source hashing, cell counts, Python magics, invalid encoding, oversized input/code, invalid schemas, omitted outputs/metadata, unevaluated calls, a mocked read-only file boundary, assignment/cell limits, and strict JSON output. Fixtures are tiny source strings in the test file; no `.ipynb` fixtures are included.

To reproduce the tests:

```sh
python3 -B -m unittest discover -s tools/notebook-execution-map/2026-10-05 -p 'test_notebook_execution_map.py' -v
```

Code is original and MIT licensed. See `provenance.json` for exact source pins and `manifest.json` for file integrity.
