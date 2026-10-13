import unittest
from datetime import date, timedelta

from coach.coaching import prescribe

TODAY = date(2026, 10, 12)


def record(days_ago, km=5, complete=True):
    return {"started_at": (TODAY - timedelta(days=days_ago)).isoformat() + "T06:00:00+00:00", "distance_km": km, "timing_complete": complete}


class CoachingTests(unittest.TestCase):
    def test_novice_plan_without_ai(self):
        plan = prescribe({"runs_per_week": 5}, [], TODAY)
        self.assertEqual(len(plan['days']), 7)
        runs = [d for d in plan['days'] if d['type'] != 'rest']
        self.assertEqual(len(runs), 3)
        self.assertTrue(all(d['duration_min'] == 15 for d in runs))
        self.assertIsNone(plan['basis']['weekly_target_km'])

    def test_recent_volume_not_more_than_five_percent(self):
        records = [record(d, 4.73) for d in [0, 3, 6, 8, 11, 14, 17, 20, 23, 26]]
        plan = prescribe({"runs_per_week": 4}, records, TODAY)
        total = sum(d['distance_km'] or 0 for d in plan['days'])
        self.assertLessEqual(total, min(sum(a['distance_km'] for a in records) / 4, 4.73*3)*1.05)
        self.assertAlmostEqual(total, plan['basis']['weekly_target_km'])
        self.assertEqual(plan, prescribe({"runs_per_week": 4}, records, TODAY))

    def test_invalid_future_missing_and_old_records_excluded(self):
        plan = prescribe({}, [record(-1), record(40), record(0, complete=False), {"distance_km": 5}], TODAY)
        self.assertEqual(plan['basis']['valid_runs_28d'], 0)

    def test_return_after_gap_reduces_volume(self):
        plan = prescribe({}, [record(10), record(17), record(24)], TODAY)
        self.assertLessEqual(plan['basis']['weekly_target_km'], 15/4*.5*1.05)
        self.assertTrue(all(d['type'] != 'steady' for d in plan['days']))

    def test_goal_is_reference_only(self):
        plan = prescribe({"goal_distance_km": 10, "goal_time_min": 60}, [], TODAY)
        self.assertEqual(plan['basis']['goal_pace_sec_km'], 360)
        self.assertTrue(all('전력' not in d['instruction'] for d in plan['days']))

    def test_no_quality_session_for_short_history(self):
        plan = prescribe({}, [record(0), record(2)], TODAY)
        self.assertTrue(all(d['type'] != 'steady' for d in plan['days']))

    def test_days_separated_for_three_day_plan(self):
        plan = prescribe({}, [], TODAY)
        self.assertEqual([d['day_index'] for d in plan['days'] if d['type'] != 'rest'], [0, 2, 5])


if __name__ == '__main__':
    unittest.main()
