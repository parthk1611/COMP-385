"""Read-only classroom code steps using the existing local prototype modules."""
import argparse
import json
from pathlib import Path
import sys


def show_data(workspace):
    import pandas as pd
    path = workspace / 'data/processed/ignition_weather_v2_development'
    contract = json.loads((path / 'predictor_contract.json').read_text())
    names = contract['spatial_candidate_predictors']
    assert 'ignition' not in names
    frame = pd.read_parquet(path / 'validation.parquet',
        filters=[('ignition_date', '=', '2017-08-09'), ('grid_id', '=', 'ofr10km_470000_40000')],
        columns=['grid_id', 'ignition_date', 'issue_time_utc', 'cwfis_missing', 'terrain_elevation_mean_m'])
    if len(frame) != 1:
        raise ValueError('Expected one pinned development example')
    return {'mode': 'archived development input inspection', 'grid_size_km': 10,
            'sample': frame.to_dict('records')[0], 'spatial_predictor_count': len(names),
            'target_is_predictor': 'ignition' in names, 'first_predictors': names[:5]}


def show_spread(workspace):
    from scripts.live_workflow import reconstruction_footprint
    from scripts.ignition_comparison import digest
    report = workspace / 'reports/week_5_completion_2026-10-16'
    source = report / 'corrected_spread_viewer.html'
    expected = json.loads((report / 'spread_viewer_audit.json').read_text())['sha256']
    if digest(source) != expected:
        raise ValueError('Saved reconstruction changed')
    payload = json.loads(source.read_text().split('window.SPREAD_VIEWER_DATA = ', 1)[1].split(';</script>', 1)[0])
    fire = next(f for f in payload['fires'] if f['id'] == '2023_COC38')
    return {'mode': 'historical final-perimeter-assisted reconstruction', 'fire': fire['id'],
            'pixel_m': fire['pixel'], 'forecast_validated': False,
            'areas_ha': {str(h): round(reconstruction_footprint(fire, h).area / 10000, 2) for h in [1, 3, 6]},
            'interpretation': 'Code decodes saved arrival times and computes areas now; it does not forecast a current fire'}


def show_workflow(workspace):
    from scripts.live_workflow import read_snapshot
    value = read_snapshot(workspace / 'data/processed/live_workflow/latest.json')
    return {'mode': 'saved reported-fire/weather snapshot', 'feed_retrieved_at_utc': value['collected_at_utc'],
            'freshness': value['freshness'], 'reported_incidents': len(value['incidents']),
            'historical_scenarios': len(value['scenarios']), 'local_notices': len(value['notices']),
            'live_ignition_probability': value['live_ignition_probability'], 'live_spread': value['live_spread'],
            'blockers': value['live_blockers']}


def show_research(workspace):
    from scripts.model_evidence import evidence_response
    evidence = evidence_response(workspace)
    results = evidence['results']
    selected = [{'candidate': r['candidate'], 'average_precision': r['average_precision'],
                 'hits': r['hits'], 'positives': r['positives']} for r in results
                if r['protocol'] == 'inner_spatial']
    return {'mode': 'display saved development evidence; no training or new evaluation',
            'geographic_comparison': selected, 'daily_review_capacity_percent': 1,
            'completed_development_fits': evidence['model_fits'],
            'earlier_fold_selection': evidence['selected']['inner_spatial'],
            'development_gate_passed': evidence['development_gates_pass']['inner_spatial'],
            'decision': 'Existing models retained. Constrained candidate finds 5/92 on exposed 2017 data but fails earlier selection folds. No live qualification.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('step', choices=['data', 'ignition', 'spread', 'workflow', 'research'])
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    sys.path.insert(0, str(workspace / 'github_iteration_1/prototype_iteration_1'))
    if args.step == 'ignition':
        from scripts.demo_model_inference import run
        run(workspace, '2017-08-09', 'ofr10km_470000_40000')
    else:
        result = {'data': show_data, 'spread': show_spread, 'workflow': show_workflow, 'research': show_research}[args.step](workspace)
        print(json.dumps(result, indent=2, allow_nan=False, default=str))
