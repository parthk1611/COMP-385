import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1] / 'reports/week_3_design_2026-10-15'
SCHEMA = json.loads((ROOT / 'interfaces.schema.json').read_text())
EXAMPLES = json.loads((ROOT / 'interface_examples.json').read_text())['examples']


def validate(name, value):
    schema = dict(SCHEMA, **{'$ref': f'#/$defs/{name}'})
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


class InterfaceContractTest(unittest.TestCase):
    def test_all_interface_examples_follow_their_schema(self):
        Draft202012Validator.check_schema(SCHEMA)
        for name, example in EXAMPLES.items():
            validate(name, example)

    def test_failed_score_cannot_be_presented_as_zero_risk(self):
        score = copy.deepcopy(EXAMPLES['IgnitionScore'])
        score.update(status='failed', probability=0., probability_status='unavailable', error='Missing model')
        with self.assertRaises(ValidationError):
            validate('IgnitionScore', score)
        score['probability'] = None
        validate('IgnitionScore', score)

    def test_forecast_request_cannot_use_final_outcomes_or_unknown_availability(self):
        request = copy.deepcopy(EXAMPLES['SpreadRequest'])
        request['mode'] = 'forecast'
        with self.assertRaises(ValidationError):
            validate('SpreadRequest', request)
        request.update(uses_final_perimeter=False, outcome_conditioned_domain=False, available_at_utc='2017-07-12T17:00:00Z')
        validate('SpreadRequest', request)

    def test_date_only_source_cannot_acquire_an_invented_observation_clock(self):
        record = copy.deepcopy(EXAMPLES['WeatherObservation'])
        record['observed_at_utc'] = '2017-07-11T17:00:00Z'
        with self.assertRaises(ValidationError):
            validate('WeatherObservation', record)


if __name__ == '__main__':
    unittest.main()
