import unittest
from datetime import date, timedelta

from coach.training import build_day, catalog, hr_zones, plan_warnings, reference
from coach.feedback import feedback
from coach.coaching import prescribe

TODAY = date(2026, 10, 13)
PROFILE = {'athlete_settings': {'benchmark_5k_min': 25, 'benchmark_5k_date': TODAY.isoformat(), 'hr_max': 190}}
BASE = {'day_index': 2, 'date': '2026-10-14'}


class TrainingTests(unittest.TestCase):
    def test_benchmark_target_not_goal_target(self):
        profile = {**PROFILE, 'goal_distance_km': 5, 'goal_time_min': 15}
        ref = reference(profile, [], TODAY)
        self.assertEqual(ref['pace_sec_km'], 300)
        self.assertFalse(ref['goal_pace_used'])
        self.assertFalse(ref['eligible_quality'])

    def test_benchmark_old_future_and_missing_are_excluded(self):
        for stamp in [TODAY + timedelta(days=1), TODAY - timedelta(days=181)]:
            ref = reference({'athlete_settings': {'benchmark_5k_min': 25, 'benchmark_5k_date': stamp.isoformat()}}, [], TODAY)
            self.assertIsNone(ref['pace_sec_km'])
        self.assertIsNone(reference({}, [], TODAY)['pace_sec_km'])

    def test_recent_record_reference_discloses_low_confidence(self):
        runs = [{'started_at': (TODAY - timedelta(days=d)).isoformat(), 'timing_complete': True, 'distance_km': 5, 'pace_sec_km': p} for d, p in [(0, 400), (3, 380), (8, 360)]]
        ref = reference({}, runs, TODAY)
        self.assertEqual(ref['confidence'], 'low')
        self.assertFalse(ref['eligible_quality'])

    def test_interval_total_includes_all_recoveries_and_warmup(self):
        day = build_day(BASE, {'type': 'interval', 'repetitions': 6, 'repeat_distance_m': 400, 'recovery_distance_m': 200, 'warmup_km': 1, 'cooldown_km': 1}, reference(PROFILE, [], TODAY))
        self.assertEqual(day['distance_km'], 5.4)
        self.assertAlmostEqual(sum(s['distance_km'] for s in day['steps']), 5.4)
        self.assertEqual(len([s for s in day['steps'] if s['role'] == 'recovery']), 5)
        self.assertTrue(day['warnings'])

    def test_long_repetition_is_slower_than_short_repetition(self):
        ref = reference(PROFILE, [], TODAY)
        short = build_day(BASE, {'type': 'interval', 'repeat_distance_m': 400}, ref)
        long = build_day(BASE, {'type': 'interval', 'repeat_distance_m': 1600}, ref)
        self.assertGreater(long['target']['pace_low_sec_km'], short['target']['pace_low_sec_km'])

    def test_heart_rate_requires_personal_settings_or_manual_range(self):
        ref = reference({}, [], TODAY)
        with self.assertRaises(ValueError):
            build_day(BASE, {'type': 'easy', 'mode': 'hr'}, ref)
        day = build_day(BASE, {'type': 'easy', 'mode': 'hr', 'hr_low': 120, 'hr_high': 140}, ref)
        self.assertEqual(day['target']['confidence'], 'manual')

    def test_automatic_ranges_keep_benchmark_provenance(self):
        ref = reference(PROFILE, [], TODAY)
        long = catalog(PROFILE, [], TODAY)['interval_targets']['1600']
        self.assertEqual(long['pace_low_sec_km'], 312)
        day = build_day(BASE, {'type': 'interval', 'repeat_distance_m': 1600,
                             'pace_low_sec_km': 312, 'pace_high_sec_km': 324}, ref)
        self.assertEqual(day['target']['confidence'], 'moderate')

    def test_pace_range_rejects_reversed_partial_and_insufficient_basis(self):
        ref = reference({}, [], TODAY)
        for spec in [{'type': 'tempo', 'mode': 'pace'}, {'type': 'tempo', 'pace_low_sec_km': 350}, {'type': 'tempo', 'pace_low_sec_km': 350, 'pace_high_sec_km': 300}]:
            with self.assertRaises(ValueError):
                build_day(BASE, spec, ref)

    def test_hr_zones_use_full_resolution_histogram(self):
        result = hr_zones({'heart_rate_seconds': {'100': 30, '140': 60, '190': 10}}, {'hr_max': 200})
        self.assertEqual(sum(z['seconds'] for z in result['zones']), 100)
        self.assertEqual(result['zones'][2]['seconds'], 60)
        self.assertFalse(hr_zones({}, {})['available'])

    def test_editing_warnings_for_adjacent_quality_and_volume(self):
        warnings = plan_warnings([{'day_index': 0, 'type': 'interval', 'distance_km': 8}, {'day_index': 1, 'type': 'tempo', 'distance_km': 8}], 10)
        self.assertTrue(any('연속' in w for w in warnings))
        self.assertTrue(any('초과' in w for w in warnings))

    def test_feedback_high_rpe_easy_is_not_reported_as_low_intensity_success(self):
        result = feedback({'distance_km': 5, 'timing_complete': True, 'heart_rate_coverage': 0, 'splits': []}, {'training_type': 'easy', 'rpe': 8}, {}, [])
        self.assertTrue(any('체감 강도' in item['text'] for item in result['opportunities']))
        self.assertTrue(any('휴식' in item['text'] for item in result['next_steps']))
        self.assertEqual(result['provider'], 'deterministic_rules')

    def test_all_workout_types_available_without_invented_paces(self):
        result = catalog({}, [], TODAY)
        self.assertEqual({r['type'] for r in result['types']}, {'rest', 'easy', 'interval', 'tempo', 'steady', 'lsd'})
        self.assertTrue(all(r['target']['pace_low_sec_km'] is None for r in result['types']))

    def test_lower_frequency_does_not_create_oversized_automatic_long_run(self):
        records = [{'started_at': (TODAY - timedelta(days=d)).isoformat(), 'timing_complete': True, 'distance_km': 5} for d in range(28)]
        plan = prescribe({'runs_per_week': 3}, records, TODAY)
        self.assertTrue(all((d.get('distance_km') or 0) <= 5.5 for d in plan['days']))
        self.assertAlmostEqual(sum(d.get('distance_km') or 0 for d in plan['days']), plan['basis']['weekly_target_km'])
