# Independent fork: immutable source, fresh one-run admission

H0 has not executed. The source remains reusable after a dated admission expires;
it provides no permanent authorization. No API key belongs in these files.

1. Pin the exact public Git commit and verify each file against
   `payload_manifest.json`. Keep the original driver unchanged (SHA256
   `cd9154a22e6139289dabdada6610acb3f4f781f304e3d72351a85da00f8a9090`).
   A standard-library byte check, run from this directory, is:

   ```python
   from pathlib import Path
   import hashlib, json
   p=Path('.')
   for name, expected in json.loads((p/'payload_manifest.json').read_text())['files'].items():
       assert hashlib.sha256((p/name).read_bytes()).hexdigest()==expected
   ```

   This verifies source only. `python -B run_h0.py --help` also launches no model.
2. Use the original Docker image and public inputs in README. Confirm the actual
   native model Input header is Google's version 2, every input's license/access
   and exact mounted paths. Observe four physical NVIDIA L4 cards and sufficient
   whole-allocation quota/capacity; do not infer this from a GPU checkbox.
3. In a **new owned work directory**, create a NEW admission based on the shipped
   invalid template and OPERATOR_ADMISSION_CONTRACT. A single local operator
   labelled `root` must actually observe every required fact. Set the new status
   `ROOT_AUTHORIZED_ONE_H0_NATIVE_CANARY`, `external_native_model_version_verified: 2`,
   `available_quota_seconds: 8400` (a conservative floor), zero active/ambiguous Gemma jobs,
   truthful required capacity/rights/profile flags and actual observation time.
   Keep `retry: false` / `submit: false`. Do not overwrite or simply redate an old record.
   The unchanged driver rejects future dates and age beyond 4,650 seconds. Separately
   refresh live dispatch checks within 300 seconds. If expired, blocked or a slot
   is lost, stop. Consumed/accepted/failed/ambiguous campaign attempts stay closed.
4. Set H0_KIT to this absolute verified source directory and H0_WORK to that new
   owned work directory containing your truthful root_admission.json. Keep
   H0_WORK in a fresh temporary private directory, for example
   `/tmp/h0_operator_<fresh-id>`, outside automatic public output exports
   (for Kaggle, outside `/kaggle/working`), because the driver writes private logs.
   Export only independently reviewed benign receipts after execution. In a
   compatible environment, invoke the underlying driver once:

   ```bash
   python -S "$H0_KIT/run_h0.py" \
     --root-admission "$H0_WORK/root_admission.json" \
     --model-dir /kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2 \
     --official-wheels /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse \
     --output "$H0_WORK/h0-output"
   ```

   Use verified exact input paths if your mount layout differs. The output must
   not exist. Original wheels remain mounted; a new owned overlay is used, with
   no host uninstall, hook/guard change or `.pth` deletion. Only owned processes
   are stopped. This is not a submission command.
5. Require H0_CHILD_PASS status PASS_REAL_COMPILER_ENDPOINT_TOOL_ROUNDTRIP and
   H0_TERMINAL_RECEIPT status PASS_H0_ONLY, no surviving owned descendants and
   independent output review. Share only reviewed manifests, redacted controls,
   counts and cleanup. **Never publish private_child.log/private_server.log**,
   environment dictionaries, credentials, headers or unreviewed model/task text.

For the campaign's native notebook bootstrap, the sole coordinator must also
verify the actual public source dataset V1/manifest, fresh existing main identity,
full metadata/terminal state and actual installed SDK request below 1 MB. This
GitHub source release creates no such dataset or native run. Before any campaign
H0 launch, root must prepare a NEW independently reviewed bootstrap that keeps raw
logs outside automatic public exports and exports only reviewed benign receipts.
The old prepared main H0 candidate has not met that gate and is not launch
qualified; keep it and all old packets unchanged. A direct independent fork pins
its own public source/inputs and admission; it does not claim an unpublished
campaign dataset exists. The historical probe cannot be a size-limit
fallback. Preserve all notebook identities, source/history and art; never compress
or archive them to fit. All original campaign launch gates remain in force.
