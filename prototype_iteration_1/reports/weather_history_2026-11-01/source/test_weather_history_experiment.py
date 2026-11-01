import unittest
import numpy as np
import pandas as pd
from scripts.weather_history_experiment import weather_history, relabel, history_values, choose_features


class WeatherHistoryTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({'grid_id':['a']*8,'ignition_date':pd.date_range('2017-05-01',periods=8).strftime('%Y-%m-%d'),
                             'cwfis_fwi':np.arange(8.),'cwfis_dmc':np.arange(8.)*2})

    def test_windows_use_only_prior_day_observations_including_current_row(self):
        f=self.frame();r=weather_history(f)
        self.assertEqual(r.loc[2,'wx_fwi_mean_3d'],1.)
        self.assertEqual(r.loc[2,'wx_fwi_delta_3d'],2.)
        self.assertEqual(r.loc[6,'wx_dmc_delta_7d'],12.)
        changed=f.copy();changed.loc[7,'cwfis_fwi']=10000
        pd.testing.assert_frame_equal(r.iloc[:7],weather_history(changed).iloc[:7])

    def test_missing_days_and_season_boundary_are_not_filled(self):
        f=self.frame().drop(index=1);r=weather_history(f)
        self.assertTrue(np.isnan(r.loc[2,'wx_fwi_mean_3d']))
        self.assertEqual(r.loc[2,'wx_fwi_count_3d'],2)
        self.assertEqual(r.loc[0,'wx_fwi_incomplete_7d'],1)

    def test_duplicate_and_invalid_dates_rejected(self):
        f=self.frame()
        with self.assertRaises(ValueError):weather_history(pd.concat([f,f.iloc[:1]]))
        f.loc[0,'ignition_date']='2019-05-01'
        with self.assertRaises(ValueError):weather_history(f)

    def test_prescribed_removal_retains_human_and_unknown_causes_and_mixed_days(self):
        f=pd.DataFrame({'grid_id':['a','b','c'],'ignition_date':['2017-05-01']*3,'ignition':[1,1,1]})
        e=pd.DataFrame({'grid_id':['a','a','b','c'],'ignition_date':['2017-05-01']*4,
                        'cause':['H-PB','H','U','U'],'fire_type':['','','','PB'],'is_prescribed':['']*4})
        r= relabel(f,e)
        self.assertEqual(r.ignition.tolist(),[1,1,0])
        self.assertEqual(r.ignition_count.tolist(),[1,1,0])

    def test_history_excludes_issue_day_and_uses_retained_events(self):
        f=pd.DataFrame({'grid_id':['ofr10km_0_0']*3,'ignition_date':['2017-05-01','2017-05-02','2017-06-02']})
        e=pd.DataFrame({'grid_id':['ofr10km_0_0'],'ignition_date':['2017-05-01']})
        r=history_values(f,e)
        self.assertEqual(r.fire_history_same_cell_30d.tolist(),[0,1,0])
        self.assertTrue(np.isnan(r.fire_history_days_since_same_cell.iloc[0]))
        self.assertEqual(r.fire_history_days_since_same_cell.iloc[2],32)

    def test_allowlist_excludes_targets_keys_and_spatial_fire_history(self):
        base={'temporal_candidate_predictors':['cwfis_fwi','fire_history_same_cell_30d'],
              'spatial_candidate_predictors':['cwfis_fwi']}
        self.assertNotIn('fire_history_same_cell_30d',choose_features(base,'inner_spatial','history_quality'))
        with self.assertRaises(ValueError):choose_features(base,'temporal','invented')


class PartitionTests(unittest.TestCase):
    def test_spatial_fit_excludes_held_cells_and_future_years(self):
        from unittest.mock import Mock,patch
        from scripts.weather_history_experiment import train_bundle
        frame=pd.DataFrame({'_year':[2013,2013,2014,2013,2013], 'inner_role':['inner_training','inner_training','inner_training','inner_validation','outer_reserved'],
                            'ignition':[0,1,1,1,0], 'cwfis_fwi':[1.,1.5,2.,3.,4.]})
        pop=pd.DataFrame({'year':[2013,2014,2013,2013],'inner_role':['inner_training','inner_training','inner_validation','outer_reserved'],'rows':[100]*4,'positives':[1]*4})
        model=Mock()
        with patch('scripts.weather_history_experiment.candidates',return_value={'lightgbm':model}):
            train_bundle(frame,pop,2014,'inner_spatial','reference',{'spatial_candidate_predictors':['cwfis_fwi']})
        self.assertEqual(model.fit.call_args.args[0].cwfis_fwi.tolist(),[1.,1.5])

    def test_future_events_cannot_change_earlier_history(self):
        from scripts.weather_history_experiment import history_values
        f=pd.DataFrame({'grid_id':['ofr10km_0_0'],'ignition_date':['2017-05-02']})
        e=pd.DataFrame({'grid_id':['ofr10km_0_0'],'ignition_date':['2017-05-01']})
        later=pd.DataFrame({'grid_id':['ofr10km_0_0'],'ignition_date':['2017-05-03']})
        pd.testing.assert_frame_equal(history_values(f,e),history_values(f,pd.concat([e,later])))

if __name__=='__main__':unittest.main()
