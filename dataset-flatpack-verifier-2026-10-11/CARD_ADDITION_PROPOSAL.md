# Proposed addition: verify the download before running examples

**Proposal only.** Root/coordinator should verify the final published version, manifest pin and package URL before applying this to existing dataset descriptions. Keep titles, slugs, licenses and all files intact. This is a reusable section for the Knee reader, Gemma packages and hidden-rerun kit; it supplies a practical first step rather than another general description.

## Suggested card section

Before running code from this dataset, verify its files against its version-specific manifest. Use the read-only `verify_flatpack.py` helper from the linked public reproduction package, with the manifest SHA-256 recorded for the exact version you attached:

```bash
python3 -I -B verify_flatpack.py /kaggle/input/<dataset-slug> \
  --manifest-sha256 <trusted-version-specific-manifest-sha256>
```

Both manifest formats in our packs are accepted. The result separates verified content from excluded metadata. A passing byte check is not a model-compatibility, scientific-validity or score claim.

Where instructions refer to original subfolders, use an explicit filename-to-path map to inspect the layout. The helper prints a checked plan and does not restore, rename, move or overwrite files. Literal double underscores in Python filenames must remain literal. Keep every existing notebook and source artifact intact.

### Coordinator binding checklist

Resolve both angle-bracket placeholders and add the actual commit-pinned helper link before publication. Match the dataset version's uploaded manifest to the published pin. Label the helper as original MIT code; leave the dataset's per-file terms unchanged. Retain current card sections and source credit. This proposal does not authorize any notebook mutation or replacement.

## Why this is needed in the inspected cards

The Gemma packages card's current snippet hashes whole files and checks them with `assert`; optimization disables those checks. Two code packs instead use a list-shaped manifest, so the Gemma snippet cannot be pasted there unchanged. The hidden-rerun kit card's restoration loop moves files, including a provided example notebook, which is unsuitable for this campaign's global notebook-preservation policy. We did not run that loop. The proposed common verifier has no mutation mode and never executes dataset code.

This package does not claim that descriptions cause votes or that any dataset's post-update ranking improved. The practical target is fewer setup mistakes and explicit release binding.
