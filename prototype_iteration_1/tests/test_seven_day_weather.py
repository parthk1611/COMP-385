from datetime import date

import numpy as np
import pandas as pd
import pytest

from scripts.seven_day_weather import MODEL, normalise, variables


def response(start='2024-06-01', end='2024-06-03'):
    times = pd.date_range(start, end, freq='h', inclusive='left', tz='UTC')
    hourly = {'time': times.strftime('%Y-%m-%dT%H:%M').tolist()}
    units = {'time': 'iso8601'}
    for name, unit in variables().items():
        hourly[name] = [50. if 'humidity' in name else 1.] * len(times)
        units[name] = unit
    return {'latitude': 50., 'longitude': -85., 'timezone': 'GMT', 'utc_offset_seconds': 0,
            'hourly': hourly, 'hourly_units': units}


def test_local_calendar_day_and_all_seven_forecast_offsets():
    locations = pd.DataFrame({'site': ['a'], 'latitude': [50.], 'longitude': [-85.]})
    frame = normalise(response(), locations, '2024-06-01', '2024-06-01', '2026-11-14T12:00Z')
    assert len(frame) == 7
    assert sorted(frame.lead.unique()) == list(range(1, 8))
    assert frame.hours.eq(24).all() and frame.rain.eq(24).all()
    assert (pd.to_datetime(frame.reference_upper_bound, utc=True)
            < pd.to_datetime(frame.issue_time, utc=True)).all()
    assert frame.model.eq(MODEL).all()


def test_missing_one_variable_cannot_be_counted_as_complete():
    doc = response()
    doc['hourly']['relative_humidity_2m_previous_day2'][12] = None
    points = pd.DataFrame({'site': ['a'], 'latitude': [50.], 'longitude': [-85.]})
    frame = normalise(doc, points, '2024-06-01', '2024-06-01', '2026-11-14T12:00Z')
    incomplete = frame[frame.lead.eq(2)].iloc[0]
    assert incomplete.hours == 23
    assert np.isnan(incomplete.temp) and np.isnan(incomplete.rain)


@pytest.mark.parametrize('change', ['units', 'time', 'location'])
def test_invalid_response_is_rejected(change):
    doc = response()
    if change == 'units': doc['hourly_units']['wind_speed_10m_previous_day1'] = 'm/s'
    if change == 'time': doc['hourly']['time'][1] = doc['hourly']['time'][0]
    if change == 'location': doc['longitude'] = -75.
    points = pd.DataFrame({'site': ['a'], 'latitude': [50.], 'longitude': [-85.]})
    with pytest.raises(ValueError):
        normalise(doc, points, '2024-06-01', '2024-06-01', '2026-11-14T12:00Z')


def test_dst_day_requires_25_hours():
    doc = response('2026-11-01', '2026-11-03')
    points = pd.DataFrame({'site': ['a'], 'latitude': [50.], 'longitude': [-85.]})
    frame = normalise(doc, points, '2026-11-01', '2026-11-01', '2026-11-14T12:00Z')
    assert frame.expected_hours.eq(25).all()
    assert frame.hours.eq(25).all()
