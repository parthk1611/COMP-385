import unittest

import pandas as pd

from scripts.geographic_transfer import PHYSICAL, select, train


class TransferTests(unittest.TestCase):
    def test_physical_contract_has_no_targets_history_or_reporting_covariates(self):
        self.assertEqual(len(PHYSICAL), len(set(PHYSICAL)))
        self.assertFalse(any("history" in f or "station" in f or "ignition" in f for f in PHYSICAL))
        self.assertIn("cg_density_168h", PHYSICAL)

    def test_held_geography_and_reserved_training_cutoffs_are_rejected(self):
        for cutoff, role in ((2016, "inner_validation"), (2018, "inner_training")):
            sample = pd.DataFrame({"inner_role": [role]})
            with self.assertRaises(ValueError):
                train(sample, pd.DataFrame(), cutoff, "physical_logistic", {})

    def test_selection_rejects_recall_loss_or_exposed_diagnostic_folds(self):
        records = [{"candidate": name, "year": year, "average_precision": .1 if name == "reference" else .2,
                    "daily_budget_recall": .1 if name == "reference" else .05}
                   for name in ("reference", "physical_logistic", "physical_monotonic") for year in (2014, 2015)]
        self.assertEqual(select(records), "reference")
        records[0]["year"] = 2017
        with self.assertRaises(ValueError):
            select(records)
