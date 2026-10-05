from dataclasses import replace
import unittest

import numpy as np

from action_sft_loss import FixtureTrajectory, action_sft_loss


def fixture(task="a", trajectory="a1", action_losses=(2., 4.), outcome="success", verified=True):
    # Two prompt tokens, one thought token, variable actions, two padding tokens.
    n = 5 + len(action_losses)
    masks = [np.zeros(n, dtype=bool) for _ in range(4)]
    masks[0][:2] = True
    masks[1][2] = True
    masks[2][3:-2] = True
    masks[3][-2:] = True
    return FixtureTrajectory("fixture/task/" + task, "fixture/trajectory/" + trajectory,
        np.arange(n, dtype=np.int64), -np.array([10., 12., 20., *action_losses, 30., 40.]),
        *masks, outcome, verified)


class LossContract(unittest.TestCase):
    def test_hierarchical_mass_and_known_loss(self):
        rows = [fixture(action_losses=(2., 4.)), fixture(trajectory="a2", action_losses=(8.,)),
                fixture(task="b", trajectory="b1", action_losses=(1.,) * 100)]
        r = action_sft_loss(rows)
        self.assertEqual(r.unique_tasks, 2)
        self.assertEqual(r.accepted_trajectories, 3)
        self.assertAlmostEqual(r.loss, 3.25)
        np.testing.assert_allclose([w.sum() for w in r.token_weights], [.25, .25, .5])
        self.assertFalse(r.training_ready)
        self.assertTrue(r.synthetic_only)

    def test_duplicate_verbose_trajectory_and_task_rows(self):
        rows = [fixture(action_losses=(2.,) * 200), fixture(task="b", trajectory="b1", action_losses=(7.,))]
        a = action_sft_loss(rows)
        b = action_sft_loss(rows + rows + [rows[0]])
        self.assertEqual(a.loss, b.loss)
        self.assertEqual(b.unique_tasks, 2)
        self.assertEqual(b.accepted_trajectories, 2)
        self.assertEqual(b.duplicate_rows, 3)
        self.assertEqual(sum(w.sum() for w in b.token_weights[2:]), 0.)
        np.testing.assert_allclose(sum(g.sum() for g in a.grad_log_probs), sum(g.sum() for g in b.grad_log_probs))

    def test_repeated_action_tokens_do_not_increase_trajectory_mass(self):
        a = action_sft_loss([fixture(action_losses=(2., 4.))])
        b = action_sft_loss([fixture(action_losses=(2., 4.) * 20)])
        self.assertAlmostEqual(a.loss, b.loss)
        self.assertAlmostEqual(a.token_weights[0].sum(), b.token_weights[0].sum())

    def test_prompt_thought_padding_have_exact_zero_gradient(self):
        row = fixture()
        r = action_sft_loss([row])
        excluded = row.prompt_mask | row.thought_mask | row.padding_mask
        self.assertTrue(np.all(r.grad_log_probs[0][excluded] == 0))
        changed = row.token_log_probs.copy()
        changed[excluded] -= 1e6
        self.assertEqual(r.loss, action_sft_loss([replace(row, token_log_probs=changed)]).loss)

    def test_finite_difference_action_and_padding_gradients(self):
        row = fixture()
        r = action_sft_loss([row])
        eps = 1e-6
        for k in range(len(row.token_ids)):
            plus = row.token_log_probs.copy(); plus[k] += eps
            minus = row.token_log_probs.copy(); minus[k] -= eps
            numeric = (action_sft_loss([replace(row, token_log_probs=plus)]).loss -
                       action_sft_loss([replace(row, token_log_probs=minus)]).loss) / (2 * eps)
            self.assertAlmostEqual(numeric, r.grad_log_probs[0][k], places=8)

    def test_failed_unknown_and_unverified_success_have_no_supervision(self):
        rows = [fixture(outcome="failure"), fixture(trajectory="a2", outcome="unknown", verified=False),
                fixture(trajectory="a3", verified=False)]
        r = action_sft_loss(rows)
        self.assertEqual(r.loss, 0.)
        self.assertEqual(r.unique_tasks, 0)
        self.assertEqual(r.accepted_trajectories, 0)
        self.assertEqual(len(r.exclusions), 3)
        self.assertTrue(all(np.all(g == 0) for g in r.grad_log_probs))
        self.assertFalse(r.training_ready)

    def test_excluded_task_does_not_dilute_accepted_task(self):
        success = fixture()
        failed = fixture(task="b", trajectory="b1", outcome="failure")
        self.assertEqual(action_sft_loss([success]).loss, action_sft_loss([success, failed]).loss)

    def test_conflicting_duplicate_identity_fails(self):
        row = fixture()
        with self.assertRaises(ValueError):
            action_sft_loss([row, replace(row, outcome="failure")])

    def test_overlap_mask_fails(self):
        row = fixture(); mask = row.action_mask.copy(); mask[0] = True
        with self.assertRaises(ValueError): action_sft_loss([replace(row, action_mask=mask)])

    def test_unclassified_token_fails(self):
        row = fixture(); mask = row.prompt_mask.copy(); mask[0] = False
        with self.assertRaises(ValueError): action_sft_loss([replace(row, prompt_mask=mask)])

    def test_nonboolean_or_misaligned_mask_fails(self):
        row = fixture()
        for mask in [row.action_mask.astype(np.int64), row.action_mask[:-1]]:
            with self.assertRaises(ValueError): action_sft_loss([replace(row, action_mask=mask)])

    def test_unknown_cannot_be_verified(self):
        with self.assertRaises(ValueError): action_sft_loss([fixture(outcome="unknown")])

    def test_nonfixture_provenance_cannot_be_admitted(self):
        with self.assertRaises(ValueError): action_sft_loss([replace(fixture(), outcome_provenance="teacher")])
        with self.assertRaises(ValueError): action_sft_loss([replace(fixture(), task_id="real-task")])

    def test_invalid_outcome_probability_or_integer_tokens_fails(self):
        row = fixture()
        for changed in [replace(row, outcome="PASS"), replace(row, outcome_verified=1),
                        replace(row, token_log_probs=np.full(row.token_ids.shape, np.nan)),
                        replace(row, token_log_probs=np.ones(row.token_ids.shape)),
                        replace(row, token_ids=row.token_ids.astype(float))]:
            with self.assertRaises(ValueError): action_sft_loss([changed])

    def test_no_action_success_fails(self):
        row = fixture(); prompt = row.prompt_mask | row.action_mask
        with self.assertRaises(ValueError):
            action_sft_loss([replace(row, prompt_mask=prompt, action_mask=np.zeros_like(prompt))])

    def test_input_order_does_not_change_loss_or_identity_mass(self):
        rows = [fixture(), fixture(trajectory="a2", action_losses=(8.,)), fixture(task="b", trajectory="b1")]
        a = action_sft_loss(rows); b = action_sft_loss(list(reversed(rows)))
        self.assertAlmostEqual(a.loss, b.loss)
        np.testing.assert_allclose([w.sum() for w in a.token_weights], list(reversed([w.sum() for w in b.token_weights])))

    def test_empty_batch_is_zero_and_not_training_ready(self):
        r = action_sft_loss([])
        self.assertEqual(r.loss, 0.)
        self.assertEqual(r.token_weights, ())
        self.assertFalse(r.training_ready)


if __name__ == "__main__":
    unittest.main(verbosity=2)
