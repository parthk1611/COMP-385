"""Compare spread parameter-selection rules using calibration fires only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.ignition_comparison import digest, save_json

POLICIES = ('area_distance_reference', 'fire_balanced_iou')
SETTINGS = ['ros_scale', 'flank_scale']
STEP = ['fire_id', 'from_observation', 'to_observation']


def validate_replays(frame, allowed_fires):
    if not len(frame) or not set(frame.fire_id).issubset(allowed_fires):
        raise ValueError('Only registered calibration fires are allowed')
    if frame.duplicated(STEP + SETTINGS).any():
        raise ValueError('Duplicate replay result')
    reference_keys = None
    for _, group in frame.groupby(SETTINGS):
        keys = set(map(tuple, group[STEP].to_numpy()))
        if reference_keys is not None and keys != reference_keys:
            raise ValueError('Candidate settings have different observation support')
        reference_keys = keys
    for column in ['observed_new_cells', 'observed_distance_m', 'hours']:
        if (frame.groupby(STEP)[column].nunique(dropna=False) != 1).any():
            raise ValueError('Observed target differs across candidate settings')
    for column in ['iou', 'recall']:
        if not frame[column].between(0, 1).all():
            raise ValueError('Missing or invalid primary replay metric')
    for column in ['even_growth_iou', 'even_growth_recall']:
        if not frame[column].fillna(0).between(0, 1).all():
            raise ValueError('Invalid replay metric')
    for column in ['observed_new_cells', 'observed_distance_m', 'hours']:
        if not (np.isfinite(frame[column]) & frame[column].gt(0)).all():
            raise ValueError('Invalid observation support')
    if frame.fire_id.nunique() < 3:
        raise ValueError('Insufficient distinct calibration fires')


def choose_setting(frame, policy):
    if policy not in POLICIES:
        raise ValueError('Unregistered selection rule')
    scores = []
    for key, group in frame.groupby(SETTINGS, sort=True):
        if policy == 'fire_balanced_iou':
            score = -float(group.groupby('fire_id').iou.mean().mean())
        else:
            distance = round(float((group.simulated_distance_m.fillna(0) / group.observed_distance_m).median()), 3)
            area = round(float(group.area_ratio.median()), 3)
            score = abs(np.log(max(distance, 1e-6))) + abs(np.log(max(area, 1e-6) / 1.3))
        scores.append((score, *key))
    return tuple(min(scores)[1:])


def selected_rows(frame, setting):
    return frame.loc[np.isclose(frame.ros_scale, setting[0]) & np.isclose(frame.flank_scale, setting[1])]


def cross_fire_validation(frame):
    records = []
    for fire in sorted(frame.fire_id.unique()):
        training = frame.loc[frame.fire_id.ne(fire)]
        validation = frame.loc[frame.fire_id.eq(fire)]
        for policy in POLICIES:
            setting = choose_setting(training, policy)
            rows = selected_rows(validation, setting)
            records.append({'fire_id': fire, 'policy': policy,
                            'training_fires': sorted(training.fire_id.unique()),
                            'training_fire_count': training.fire_id.nunique(),
                            'steps': len(rows), 'ros_scale': setting[0], 'flank_scale': setting[1],
                            'iou': float(rows.iou.mean()), 'recall': float(rows.recall.mean()),
                            'even_growth_iou': float(rows.even_growth_iou.fillna(0).mean()),
                            'even_growth_recall': float(rows.even_growth_recall.fillna(0).mean())})
    return pd.DataFrame(records)


def summarize_validation(frame):
    summary = frame.groupby('policy')[['iou', 'recall', 'even_growth_iou', 'even_growth_recall']].mean()
    pivot = frame.pivot(index='fire_id', columns='policy', values='iou')
    delta = (pivot.fire_balanced_iou - pivot.area_distance_reference).to_numpy()
    indices = np.random.default_rng(385).integers(0, len(delta), (2000, len(delta)))
    interval = np.quantile(delta[indices].mean(axis=1), [.025, .975]).tolist()
    # An improvement must survive the paired fire-bootstrap interval before changing the default.
    selected = 'fire_balanced_iou' if interval[0] > 0 else 'area_distance_reference'
    return {'fire_macro_metrics': summary.to_dict(orient='index'),
            'paired_iou_difference': {'mean': float(delta.mean()), 'ci95': interval,
                                      'method': 'paired bootstrap over entire calibration fires'},
            'selected_policy': selected, 'scoreable_calibration_fires': len(delta)}


def run(workspace, output):
    if output.exists():
        raise FileExistsError('Use a new output directory')
    source = workspace / 'data/processed/spread_replay_corrected_v2/spread_simulator_calibration_steps_v1.csv'
    plan_path = workspace / 'reports/week_5_completion_2026-10-16/completion_protocol.json'
    plan = json.loads(plan_path.read_text())
    allowed = set(plan['spread_calibration_fires'])
    if allowed & set(plan['spread_holdout_fires']):
        raise ValueError('Calibration and holdout IDs overlap')
    output.mkdir(parents=True)
    save_json(output / 'protocol.json', {
        'calibration_source': str(source), 'calibration_sha256': digest(source),
        'source_protocol_sha256': digest(plan_path), 'policies': list(POLICIES),
        'selection': 'Leave one entire calibration fire out; parameter selection uses remaining fires only',
        'decision': 'Change default only if lower paired fire-bootstrap IoU delta bound exceeds zero',
        'holdout_observations_read': False, 'old_simulator_or_final_outputs_overwritten': False,
        'scope': 'Internal calibration robustness study; no fresh forecast validation',
        'code_sha256': digest(Path(__file__)),
    })
    frame = pd.read_csv(source, dtype={'fire_id': str})
    validate_replays(frame, allowed)
    validation = cross_fire_validation(frame)
    validation.to_json(output / 'cross_fire_results.json', orient='records', indent=2)
    validation.drop(columns='training_fires').to_csv(output / 'cross_fire_results.csv', index=False)
    result = summarize_validation(validation)
    result.update(setting=list(choose_setting(frame, result['selected_policy'])),
                  scoreable_observation_steps=len(frame[STEP].drop_duplicates()),
                  candidate_settings=len(frame[SETTINGS].drop_duplicates()),
                  unscoreable_registered_fires=sorted(allowed - set(frame.fire_id)),
                  mode='retrospective_reconstruction_final_perimeter_assisted',
                  forecast_validation=False,
                  limitations=['These calibration fires and candidate settings were already explored previously.',
                               'The old holdout is already exposed and was not reopened or retuned here.',
                               'Matched-area even-growth uses simulator area and is a conditional shape benchmark.',
                               'Perimeter-assisted input and retrospective weather prevent operational forecast claims.'])
    save_json(output / 'results.json', result)
    save_json(output / 'settings_candidate.json', {
        'ros_scale': result['setting'][0], 'flank_scale': result['setting'][1],
        'repair_burn_scar': True, 'selection_policy': result['selected_policy'],
        'propagation_revision': 'surface-barrier-clearance-v2',
        'mode': result['mode'], 'forecast_validated': False,
        'source_sha256': digest(source), 'default_runtime_updated': False,
    })
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.workspace.resolve(), args.output_dir.resolve())
