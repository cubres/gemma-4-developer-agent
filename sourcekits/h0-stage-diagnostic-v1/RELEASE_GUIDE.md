# H0 stage diagnostic R2: source and portable fixture guide

This release contains a small diagnostic entrypoint and seven invented fixture
tests. It has not established a new model result, H0 compatibility, score,
thinking clipping or speed gain. Tests use local invented files and a mocked
helper; they never execute the original H0 helper or a model.

The five files under `payload/` retain the frozen R2 bytes. Their manifest's
`UNPUBLISHED` status and null future dataset ID/version describe **build-time
provenance**. They remain immutable after publication. Actual public availability,
native ID/version and downloaded byte checks belong in a separate root receipt
made after real publication; do not infer them from or backfill this manifest.
Publication creates no compute authority.

Original input: [immutable H0 offline V1 source](https://github.com/cubres/gemma-4-developer-agent/tree/25827ba19a82c5cb62273ba774fa46e8d46a398a/sourcekits/h0-offline-v1),
commit `25827ba19a82c5cb62273ba774fa46e8d46a398a`; native
[dataset V1](https://www.kaggle.com/datasets/prvsiyan/gemma-h0-endpoint-compatibility-kit/versions/1),
ID12718547. This separate observer does not modify that original kit.

## Prepare the four original pin files for fixture checks

Keep this release's `payload/` directory and root test file in place. The
unchanged test's development-tree default for `ORIGINAL` is not portable on its
own. Download these **four files only** into a sibling `h0-offline-v1` directory,
or choose an explicit local directory containing them:

* [BUNDLE_MANIFEST.json](https://raw.githubusercontent.com/cubres/gemma-4-developer-agent/25827ba19a82c5cb62273ba774fa46e8d46a398a/sourcekits/h0-offline-v1/BUNDLE_MANIFEST.json)
* [private_h0_flat_bootstrap.py](https://raw.githubusercontent.com/cubres/gemma-4-developer-agent/25827ba19a82c5cb62273ba774fa46e8d46a398a/sourcekits/h0-offline-v1/private_h0_flat_bootstrap.py)
* [core_run_h0.py](https://raw.githubusercontent.com/cubres/gemma-4-developer-agent/25827ba19a82c5cb62273ba774fa46e8d46a398a/sourcekits/h0-offline-v1/core_run_h0.py)
* [public_receipt_serializer.py](https://raw.githubusercontent.com/cubres/gemma-4-developer-agent/25827ba19a82c5cb62273ba774fa46e8d46a398a/sourcekits/h0-offline-v1/public_receipt_serializer.py)

The fixture reads those exact public bytes for the four pinned hash checks and
copies them into an invented input directory. It does not import or execute any
of those four original files. Expected hashes are `PINS` in the new entrypoint.
Four files are sufficient for these mocked fixtures. A **real helper run requires
all13 original V1 kit files**, its complete membership/manifest checks, legitimate
model/wheel inputs and a new actual admission; the four-file fixture setup is not
a runtime kit.

## Run the stdlib fixtures with the explicit original-kit override

Use Python3.12 and adjust `release` to this release's local root. Set `m.ORIGINAL`
after importing the test module and before loading/running its suite:

```python
from pathlib import Path
import importlib.util
import unittest

release = Path('/absolute/path/to/h0-stage-diagnostic-r2')
spec = importlib.util.spec_from_file_location(
    'h0_stage_fixtures', release / 'test_h0_stage_diagnostic.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.ORIGINAL = release.parent / 'h0-offline-v1'
# Alternatively: m.ORIGINAL = Path('/explicit/path/to/the/four/original/files')

suite = unittest.defaultTestLoader.loadTestsFromModule(m)
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful()
```

Seven fixtures cover milestones, privacy, path/mode/symlink rejection,
oversize/partial/inconsistent JSON, source pins, exact arguments and preservation
of a mocked nonzero helper exit. The aggregate-read boundary fixture proves a
next file exceeding the remaining budget is rejected before reading it. Tiny
invented temporary fixtures remain on disk; no notebook is created or deleted.
No Kaggle account, weights, scientific data, GPU or network is used by the suite
after the four pin files have been acquired. This guide's public-copy example
has not been executed by its staging author; root will verify the actual public
copy once after publication.

## Future real use remains separately gated

The diagnostic's fixed enum is an observation of a bounded private artifact,
not positive H0 acceptance. Its original helper/core/serializer, public receipt,
once behavior and deadlines remain enforced. V34/native360225179 is closed.
Any future campaign GPU attempt requires a **new human revised-attempt exception**,
fresh all11 root checks, actual public input ID/version/hash evidence, quota and
capacity, external once and exact notebook/metadata/installed-SDK preservation
review. The source and invalid/incomplete fixture metadata grant none of these.
Preserve every existing notebook, version, identity, source, history and artwork.

New observer source is Apache-2.0; see `payload/LICENSE` and `payload/NOTICE`.
Original model, wheel, competition and original-kit terms remain separate.
