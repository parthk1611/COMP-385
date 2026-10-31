import unittest

import pandas as pd

from scripts.spread_refinement import choose_setting, cross_fire_validation, validate_replays


def replay_rows():
    rows = []
    for fire, ious in [('a', [.1, .3]), ('b', [.2, .4]), ('c', [.15, .25])]:
        for scale, iou in zip([.5, 1.2], ious):
            rows.append({'fire_id': fire, 'from_observation': 0, 'to_observation': 1,
                         'ros_scale': scale, 'flank_scale': .25, 'iou': iou,
                         'recall': .5, 'even_growth_iou': .1, 'even_growth_recall': .4,
                         'simulated_distance_m': 100 * scale, 'observed_distance_m': 100,
                         'area_ratio': 1.3, 'observed_new_cells': 10, 'hours': 12})
    return pd.DataFrame(rows)


class SpreadRefinementTests(unittest.TestCase):
    def test_reserved_fires_and_duplicate_steps_are_rejected(self):
        frame = replay_rows()
        with self.assertRaises(ValueError):
            validate_replays(frame, {'a', 'b'})
        with self.assertRaises(ValueError):
            validate_replays(pd.concat([frame, frame.iloc[:1]]), {'a', 'b', 'c'})

    def test_candidate_settings_must_cover_the_same_observations(self):
        with self.assertRaises(ValueError):
            validate_replays(replay_rows().iloc[:-1], {'a', 'b', 'c'})

    def test_observed_targets_cannot_change_between_settings(self):
        frame = replay_rows()
        frame.loc[0, 'observed_new_cells'] = 11
        with self.assertRaises(ValueError):
            validate_replays(frame, {'a', 'b', 'c'})

    def test_fire_balancing_prevents_repeated_steps_from_dominating(self):
        frame = replay_rows()
        frame.loc[frame.fire_id.eq('a'), 'iou'] = [.9, 0]
        frame.loc[~frame.fire_id.eq('a'), 'iou'] = [0, .8, 0, .8]
        repeated = pd.concat([frame, *[frame[frame.fire_id.eq('a')] for _ in range(20)]])
        self.assertEqual(choose_setting(repeated, 'fire_balanced_iou'), (1.2, .25))

    def test_entire_fire_is_excluded_before_setting_selection(self):
        result = cross_fire_validation(replay_rows())
        self.assertEqual(len(result), 6)
        self.assertTrue((result.training_fire_count == 2).all())
        for row in result.itertuples():
            self.assertNotIn(row.fire_id, row.training_fires)

    def test_unknown_selection_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_setting(replay_rows(), 'final_test_score')

    def test_missing_primary_metrics_and_nonpositive_observations_are_rejected(self):
        for column, value in [('iou', float('nan')), ('recall', float('nan')),
                              ('observed_new_cells', 0), ('observed_distance_m', 0)]:
            frame = replay_rows()
            frame.loc[frame.fire_id.eq('a'), column] = value
            with self.assertRaises(ValueError):
                validate_replays(frame, {'a', 'b', 'c'})


if __name__ == '__main__':
    unittest.main()
