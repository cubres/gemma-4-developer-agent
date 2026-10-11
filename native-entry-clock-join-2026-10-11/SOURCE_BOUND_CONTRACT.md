# Source and receipt contract

All implementation in this directory is original integration tooling. It imports no organizer or model package during planning/tests. The dormant coordinated entry calls the existing owned arm from its already-hashed exact bytes; it neither includes nor changes that implementation.

## Frozen upstream boundaries

| Boundary | SHA-256 |
|---|---|
| Retained owned native arm | `d0134b99e2544bed8f8a3d24d1d00cf1f74e19be691e315e08474fb7716012e2` |
| Retained owned helper | `d44f8ab1bb3317b457595f353ea94fc861f518dd077acb9fdd92fd644c325833` |
| Original R3 receipt adapter | `80931c14191502008be59fb0a3a4ef46a9373edfe64f61fd39c224744ec7c8f0` |
| Original passive collector | `316dfa7a05dd54ce51b54e616e4cfe9b58d7fe1e95c7355df521b62fa55810eb` |
| Original R4 gate | `511518072a7ddc236867ae96d653f1be37b371959efc81a78fe4535359d378a8` |

The entry freezes six organizer schema/context/runner/evaluator/verifier source hashes and the retained owned arm/recorder/collector hashes as metadata. No third-party implementation, task corpus, model output, snapshot, credentials or submission contents appear in this public package. Exact hashes are consistency/provenance evidence only.

## Lifecycle

1. Before the original installer can mutate anything, save `Evaluator.evaluate_task`, `Evaluator._run_agent_sandbox`, the evaluator module's `verify_task`, and the owned arm's `install_timing`.
2. Verify the source/runtime boundaries. Invoke the original installer and preserve its return. Capture its resulting sandbox function and signature.
3. Permit only the next declared task and one active async call. The original passive collector surrounds that call without changing its arguments, return or exception.
4. Attempt all saved restorations, even after partial install failure or cancellation. Restoration failures are separately counted. They never mask an original exception; absent an original exception, a failed restoration raises HOLD.

## Sidecar

The source contract and future protocol must agree before any sidecar creation. Read the bounded existing raw arm receipt, preserving its exact bytes. Validate the repo/planned order, helper pin, raw aliases, explicit errors and exact-integer pytest exits. Compare observed clocks to the full ordered planned denominator. A caught error or unsupported/missing exit is HOLD; exits 0 and 1 do not themselves prove that actual tests ran.

The new sidecar is created with exclusive binary create mode. It binds the exact raw protocol and arm hashes, all reviewed source hashes and the entry source hash. Missing/UNKNOWN clocks retain no inferred policy values. An absent raw receipt creates no sidecar. A collision preserves the existing file. The coordinator owes a trusted output parent, stable raw files and no concurrent writer.

The sidecar augments the existing R3 adapter's clock contract. It does not modify the raw arm, JUnit captures or any prior receipt. R3/R4 still require the actual final XML bytes, ordered invocation windows, strict-verifier route and all other admission evidence. No clock sidecar establishes native authenticity.

## Packaging and deadlines

The read-only planner binds every prepared file to the supplied hash manifest and the saved build's cross-links. It retains prepared-only status and never converts the saved build into an accepted-version or runtime claim. Its equal-length loader simulation checks the entire parsed notebook and leaves all existing files untouched. Saved SDK wire spare does not qualify a future SDK request.

A future bootstrap must use the original first-cell origin and a single pinned current protocol envelope. `bootstrap_budget.py` refuses a changed/type-drifted origin or exhausted envelope; its explicit cleanup tail must fit session headroom. The old bootstrap's affine deadline and stale nested budget remain preserved source evidence, never fallback defaults. Static AST recognition has a deliberately limited syntax scope.

`entry_command.py` returns an argv list without executing it. The original child program rechecks source/manifest hashes, compiles those same entry bytes and calls the dormant API only when a separately authorized coordinator executes the route. The future protocol must pin that command source too. A complete sidecar produces a review-required child result; HOLD produces exit 2. Neither result authorizes a submission.
