"""Transparent training ranges from actual benchmarks/history, never goal pace."""
import math
from datetime import date, datetime, timedelta, timezone
from statistics import median

TITLES = {'rest': '회복', 'easy': '이지런 / 걷기', 'interval': '거리 인터벌',
          'tempo': '템포런', 'steady': '지속주', 'lsd': 'LSD · 장거리 저강도'}
QUALITY = {'interval', 'tempo'}


def history(analyses, today=None, days=90):
    today = today or datetime.now(timezone.utc).date()
    result = []
    for a in analyses:
        try:
            day = date.fromisoformat(a['started_at'][:10])
            km = float(a.get('distance_km', 0))
            if 0 <= (today - day).days < days and a.get('timing_complete') and math.isfinite(km) and km > 0:
                result.append((day, a))
        except (ValueError, TypeError, KeyError):
            pass
    return result


def reference(profile, analyses, today=None):
    today = today or datetime.now(timezone.utc).date()
    settings = profile.get('athlete_settings') or {}
    recent = history(analyses, today, 28)
    paced = [a['pace_sec_km'] for _, a in history(analyses, today) if
             isinstance(a.get('pace_sec_km'), (float, int)) and 120 <= a['pace_sec_km'] <= 1200 and a['distance_km'] >= 1.5]
    candidates = []
    for distance, key in [(5, 'benchmark_5k_min'), (10, 'benchmark_10k_min')]:
        minutes = settings.get(key)
        stamp = settings.get(f'benchmark_{distance}k_date') or settings.get('benchmark_date')
        try:
            age = (today - date.fromisoformat(stamp)).days
            if minutes and math.isfinite(float(minutes)) and 0 <= age <= 180:
                pace = float(minutes) * 60 * (5 / distance) ** 1.06 / 5
                candidates.append(pace)
        except (ValueError, TypeError):
            pass
    if candidates:
        # Use the slower result when two actual results disagree; goals are never inputs.
        pace = max(candidates)
        source, confidence = '실제 5K/10K 기록 · Riegel 지수 1.06 환산', 'moderate'
    elif len(paced) >= 3:
        paced.sort()
        pace = paced[max(0, int((len(paced) - 1) * .25))]
        source, confidence = '최근 90일 유효 기록의 빠른 쪽 사분위 · 보수적인 참고 범위', 'low'
    else:
        pace = None
        source, confidence = '페이스 근거 부족 · 실제 5K/10K 기록 또는 유효 러닝 3회 필요', 'insufficient'
    experienced = len(recent) >= 6 and len({(today - d).days // 7 for d, _ in recent}) >= 3
    km7 = sum(a['distance_km'] for d, a in recent if (today - d).days < 7)
    eligible = experienced and km7 >= 10
    return {'pace_sec_km': round(pace, 1) if pace else None, 'source': source, 'confidence': confidence,
            'eligible_quality': eligible, 'valid_runs_28d': len(recent), 'distance_7d_km': round(km7, 2),
            'median_recent_km': round(median([a['distance_km'] for _, a in recent]), 2) if recent else None,
            'longest_recent_km': max([a['distance_km'] for _, a in recent], default=None),
            'goal_pace_used': False, 'hr_max': settings.get('hr_max'), 'lthr': settings.get('lthr')}


def targets(kind, ref):
    factors = {'easy': (1.2, 1.45), 'steady': (1.12, 1.22), 'tempo': (1.06, 1.12),
               'interval': (.98, 1.04), 'lsd': (1.25, 1.5), 'rest': (None, None)}
    low, high = factors[kind]
    pace = ref['pace_sec_km']
    hr = None
    if ref.get('lthr') and kind != 'rest':
        bounds = {'easy': (.75, .85), 'steady': (.85, .94), 'tempo': (.95, 1),
                  'interval': (1, 1.05), 'lsd': (.75, .85)}[kind]
        hr = [round(ref['lthr'] * n) for n in bounds]
    elif ref.get('hr_max') and kind != 'rest':
        bounds = {'easy': (.65, .78), 'steady': (.75, .84), 'tempo': (.85, .9),
                  'interval': (.9, .95), 'lsd': (.65, .75)}[kind]
        hr = [round(ref['hr_max'] * n) for n in bounds]
    if hr and ref.get('hr_max'):
        hr = [min(v, ref['hr_max']) for v in hr]
    rpe = {'easy': [2, 3], 'steady': [3, 5], 'tempo': [6, 7], 'interval': [7, 8], 'lsd': [2, 3], 'rest': [0, 1]}[kind]
    return {'mode': 'pace' if pace and low else 'hr' if hr else 'rpe',
            'pace_low_sec_km': round(pace * low, 1) if pace and low else None,
            'pace_high_sec_km': round(pace * high, 1) if pace and high else None,
            'hr_low': hr[0] if hr else None, 'hr_high': hr[1] if hr else None,
            'rpe_low': rpe[0], 'rpe_high': rpe[1], 'basis': ref['source'], 'confidence': ref['confidence']}


def interval_target(ref, meters):
    target = targets('interval', ref)
    if meters >= 1200 and ref.get('pace_sec_km'):
        target['pace_low_sec_km'] = round(ref['pace_sec_km'] * 1.04, 1)
        target['pace_high_sec_km'] = round(ref['pace_sec_km'] * 1.08, 1)
    return target


def catalog(profile, analyses, today=None):
    ref = reference(profile, analyses, today)
    return {'version': 'training-1.1.0', 'reference': ref,
            'types': [{'type': kind, 'title': title, 'target': targets(kind, ref)} for kind, title in TITLES.items()],
            'interval_distances_m': [200, 400, 600, 800, 1000, 1200, 1600, 2000],
            'interval_targets': {str(m): interval_target(ref, m) for m in [200, 400, 600, 800, 1000, 1200, 1600, 2000]},
            'limitations': ['범위는 시작점입니다. 실제 경기 기록도 일일 컨디션을 보장하지 않습니다.',
                            '이지런 평균을 경기 능력으로 단정하지 않습니다. 기록만 사용한 추천은 신뢰도가 낮습니다.',
                            '짧은 인터벌의 심박은 늦게 반응하므로 페이스·체감 강도를 함께 보세요.',
                            '고강도 자동 편성은 최근 28일 6회·3개 주·최근 7일 10km 이상에서만 허용합니다.']}


def build_day(base, spec, ref):
    kind = spec['type']
    target = interval_target(ref, spec.get('repeat_distance_m', 400)) if kind == 'interval' else targets(kind, ref)
    target['mode'] = spec.get('mode') or target['mode']
    if target['mode'] == 'hr' and target['hr_low'] is not None:
        target.update(basis='직접 설정한 역치심박 비율' if ref.get('lthr') else '직접 설정한 최대심박 비율', confidence='configured_hr')
    elif target['mode'] == 'rpe':
        target.update(basis='훈련 종류별 체감 강도 가이드', confidence='guide')
    for low, high in [('pace_low_sec_km', 'pace_high_sec_km'), ('hr_low', 'hr_high')]:
        if spec.get(low) is not None or spec.get(high) is not None:
            if spec.get(low) is None or spec.get(high) is None or spec[low] > spec[high]:
                raise ValueError('목표 범위의 시작과 끝을 올바르게 함께 입력하세요.')
            automatic = target.get(low) is not None and abs(spec[low] - target[low]) <= .6 and abs(spec[high] - target[high]) <= .6
            target.update({low: spec[low], high: spec[high]})
            if not automatic:
                target.update(basis='직접 조정한 범위', confidence='manual')
    if kind != 'rest' and target['mode'] == 'pace' and target['pace_low_sec_km'] is None:
        raise ValueError('페이스 근거가 없습니다. 실제 기록을 입력하거나 체감 강도를 선택하세요.')
    if kind != 'rest' and target['mode'] == 'hr' and target['hr_low'] is None:
        raise ValueError('최대·역치 심박을 설정하거나 심박 범위를 직접 입력하세요.')
    distance = spec.get('distance_km')
    duration = spec.get('duration_min')
    steps = []
    warnings = []
    if kind in QUALITY and not ref['eligible_quality']:
        warnings.append('최근 훈련 기반이 부족합니다. 고강도 자동 추천은 제한되며 이 편성은 직접 선택한 훈련입니다.')
    if kind == 'interval':
        repeat = spec.get('repetitions', 4)
        meters = spec.get('repeat_distance_m', 400)
        recovery = spec.get('recovery_distance_m', 200)
        warmup, cooldown = spec.get('warmup_km', 1), spec.get('cooldown_km', 1)
        distance = round(warmup + cooldown + (repeat * meters + (repeat - 1) * recovery) / 1000, 3)
        duration = None
        steps.append({'role': 'warmup', 'title': '워밍업', 'distance_km': warmup, 'target': targets('easy', ref)})
        for i in range(repeat):
            steps.append({'role': 'work', 'title': f'{i+1}회 · {meters}m', 'distance_km': meters / 1000, 'target': target})
            if i < repeat - 1 and recovery:
                steps.append({'role': 'recovery', 'title': f'{recovery}m 회복 조깅/걷기', 'distance_km': recovery / 1000, 'target': targets('easy', ref)})
        steps.append({'role': 'cooldown', 'title': '쿨다운', 'distance_km': cooldown, 'target': targets('easy', ref)})
    elif kind != 'rest':
        if distance is None and duration is None:
            duration = 15 if not ref['valid_runs_28d'] else 30
        if kind == 'tempo':
            steps.extend([{'role': 'warmup', 'title': '워밍업 10분 (별도)', 'duration_min': 10, 'target': targets('easy', ref)},
                          {'role': 'work', 'title': '템포 구간', 'distance_km': distance, 'duration_min': duration, 'target': target},
                          {'role': 'cooldown', 'title': '쿨다운 10분 (별도)', 'duration_min': 10, 'target': targets('easy', ref)}])
        else:
            steps.append({'role': 'work', 'title': TITLES[kind], 'distance_km': distance, 'duration_min': duration, 'target': target})
    else:
        distance = duration = None
    if kind == 'lsd' and distance and ref.get('longest_recent_km') and distance > ref['longest_recent_km'] * 1.1:
        warnings.append('최근 최장 거리보다 10% 이상 깁니다. 거리 증가와 피로를 함께 확인하세요.')
    instruction = {'rest': '휴식 또는 편안한 걷기.', 'easy': '대화가 가능한 강도. 필요하면 걷기를 섞으세요.',
                   'interval': '워밍업 후 반복 구간과 회복을 교대로 진행하세요. 전력 질주를 목표로 하지 않습니다.',
                   'tempo': '리듬을 유지할 수 있는 강도. 워밍업·쿨다운 10분씩은 본훈련 외에 포함합니다.',
                   'steady': '일정한 리듬의 지속주. 후반에도 호흡과 자세를 유지하세요.',
                   'lsd': '거리보다 여유 있는 호흡을 우선하는 장거리 저강도 러닝.'}[kind]
    return {**base, 'type': kind, 'title': TITLES[kind], 'distance_km': distance, 'duration_min': duration,
            'instruction': instruction, 'target': target, 'steps': steps, 'warnings': warnings,
            'workout_spec': spec, 'edited': True}


def plan_warnings(days, weekly_target):
    result = []
    quality = [d['day_index'] for d in days if d['type'] in QUALITY]
    if len(quality) > 1:
        result.append('고강도 훈련이 주 2회 이상입니다. 자동 계획은 주 1회를 권장합니다.')
    if any(b - a <= 1 for a, b in zip(quality, quality[1:])):
        result.append('고강도 훈련이 연속된 날짜에 있습니다. 사이에 회복일을 두세요.')
    known = sum(d.get('distance_km') or 0 for d in days)
    if weekly_target and known > weekly_target + .01:
        result.append(f'편집한 명시적 거리 합계 {known:.2f}km가 자동 계획 기준 {weekly_target:.2f}km를 초과합니다. 시간 훈련·워밍업 거리는 추가될 수 있습니다.')
    if any(d['type'] == 'tempo' for d in days):
        result.append('템포런의 워밍업·쿨다운 거리는 본훈련 거리 외에 추가됩니다. 총 부하를 확인하세요.')
    return result


def hr_zones(analysis, settings):
    maximum = settings.get('hr_max')
    if not maximum:
        return {'available': False, 'reason': '최대심박을 설정하면 영역 시간을 계산합니다. 기록의 최고심박을 최대심박으로 가정하지 않습니다.'}
    bands = [(.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1)]
    zones = [{'zone': i + 1, 'low_bpm': round(lo * maximum), 'high_bpm': round(hi * maximum), 'seconds': 0.0} for i, (lo, hi) in enumerate(bands)]
    # Full-resolution histogram is generated by the engine; chart downsampling is not used for zones.
    histogram = analysis.get('heart_rate_seconds') or {}
    below = above = 0
    for bpm, seconds in histogram.items():
        ratio = float(bpm) / maximum
        if ratio < .5:
            below += seconds
        elif ratio > 1:
            above += seconds
        else:
            index = min(4, max(0, int(round(ratio * 10, 8)) - 5))
            zones[index]['seconds'] += seconds
    return {'available': bool(histogram), 'basis': '직접 설정한 최대심박의 50–100%', 'hr_max': maximum,
            'zones': zones, 'below_seconds': below, 'above_seconds': above,
            'covered_seconds': sum(histogram.values())}
