"""Evidence-linked deterministic coaching, separate from numerical analysis."""
from .training import catalog, history, hr_zones


def feedback(analysis, notes, profile, analyses):
    strengths, opportunities, next_steps = [], [], []
    def add(items, text, **evidence):
        items.append({'text': text, 'evidence': evidence})
    distance = analysis.get('distance_km', 0)
    if distance:
        add(strengths, f'{distance:.3f}km의 훈련 기록을 남겼습니다. 일관된 기록이 다음 계획의 근거가 됩니다.', distance_km=distance)
    cv = analysis.get('pace_variability_pct')
    kind = notes.get('training_type', 'unspecified')
    if cv is not None and kind != 'interval':
        if cv <= 8:
            add(strengths, f'유효 이동 구간의 페이스 변동이 {cv:.1f}%로 비교적 일정했습니다.', pace_variability_pct=cv)
        elif cv >= 15:
            add(opportunities, f'페이스 변동이 {cv:.1f}%입니다. 신호등·경사·의도한 가속을 제외하고 리듬이 흔들린 구간을 확인하세요.', pace_variability_pct=cv)
    drift = analysis.get('heart_rate_drift_pct')
    if drift is not None and kind in {'easy', 'steady', 'lsd'}:
        if abs(drift) <= 5:
            add(strengths, f'후반의 심박/속도 비율 변화가 {drift:.1f}%로 작았습니다.', heart_rate_drift_pct=drift)
        elif drift > 5:
            add(opportunities, f'후반 심박/속도 비율이 {drift:.1f}% 증가했습니다. 더위·경사·수분·피로 등 맥락과 함께 확인하세요.', heart_rate_drift_pct=drift)
    rpe = notes.get('rpe')
    if rpe is not None:
        if kind in {'easy', 'lsd'} and rpe >= 6:
            add(opportunities, f'저강도 훈련으로 기록했지만 체감 강도는 {rpe}/10입니다. 다음 저강도 훈련에서는 속도를 낮추거나 시간을 줄이세요.', rpe=rpe, training_type=kind)
        elif rpe <= 4:
            add(strengths, f'직접 기록한 체감 강도는 {rpe}/10입니다. 편안한 훈련을 이어갈 기준으로 활용하세요.', rpe=rpe)
    splits = [s for s in analysis.get('splits', []) if not s.get('partial') and s.get('pace_sec_km')]
    if len(splits) >= 2 and kind not in {'interval', 'unspecified'}:
        change = (splits[-1]['pace_sec_km'] / splits[0]['pace_sec_km'] - 1) * 100
        if change > 10:
            add(opportunities, f'마지막 완전 1km 구간이 첫 구간보다 {change:.1f}% 느립니다. 초반 강도와 코스 차이를 확인하세요.', first_split=splits[0]['pace_sec_km'], last_split=splits[-1]['pace_sec_km'])
    if not analysis.get('timing_complete'):
        add(opportunities, '시간 결측이 있어 페이스와 강도 판단을 제한했습니다.', timing_complete=False)
    if analysis.get('heart_rate_coverage', 0) < .75:
        add(opportunities, '심박 표본이 부족해 심박 기반 평가를 제한했습니다. 센서 기록 여부를 확인하세요.', coverage=analysis.get('heart_rate_coverage'))
    if kind == 'unspecified':
        add(opportunities, '훈련 의도가 입력되지 않았습니다. 이지런·인터벌 등 훈련 종류와 체감 강도를 기록하면 의도와 결과를 비교할 수 있습니다.')
    ref = catalog(profile, analyses)['reference']
    if rpe is not None and rpe >= 8:
        add(next_steps, '다음 훈련은 휴식 또는 짧은 저강도 러닝으로 잡고 회복 상태를 먼저 확인하세요.', rpe=rpe)
    elif ref['eligible_quality']:
        add(next_steps, '저강도 훈련을 중심으로 유지하고, 이번 주 고강도 훈련이 없다면 인터벌 또는 템포런 하나를 선택하세요.', eligible_quality=True)
    else:
        add(next_steps, '현재는 저강도 훈련과 회복일의 규칙적인 배치를 우선하세요. 고강도 자동 추천에 필요한 최근 훈련 기반이 아직 부족합니다.', valid_runs_28d=ref['valid_runs_28d'], distance_7d_km=ref['distance_7d_km'])
    if ref['confidence'] == 'insufficient':
        add(next_steps, '실제 5K/10K 기록을 입력하거나 기존 러닝을 추가하면 목표 페이스 범위를 제시할 수 있습니다.')
    recent = history(analyses)
    return {'version': 'coach-1.1.0', 'provider': 'deterministic_rules', 'strengths': strengths,
            'opportunities': opportunities, 'next_steps': next_steps,
            'basis': {'history_runs_90d': len(recent), 'training_type': kind, 'rpe': rpe, 'reference': ref},
            'heart_rate_zones': hr_zones(analysis, profile.get('athlete_settings') or {}),
            'limitations': ['의료 진단이나 부상 치료 처방이 아닙니다.',
                            '심박/속도 변화는 경사·기온·센서 오차의 영향을 받으며 유산소 능력으로 단정하지 않습니다.',
                            '가민 독자 알고리즘의 운동 효과·회복 시간·바디 배터리를 재현하거나 추정하지 않습니다.']}
