"use client";
import { useEffect, useState } from 'react';
import { api, jsonBody, pace } from '@/lib/api';
import type { Analysis, Feedback, Run } from '@/lib/types';

const number = (v: number | null | undefined, digits = 1) => v == null ? '데이터 없음' : v.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const clock = (v: number | null | undefined) => v == null ? '데이터 없음' : `${Math.floor(Math.round(v) / 60)}:${String(Math.round(v) % 60).padStart(2, '0')}`;
const extraFields = [
  ['primary_benefit', '기본 운동 효과', 'text'], ['self_evaluation', '자기 평가', 'text'],
  ['calories_active_kcal', '활동 칼로리', 'kcal'], ['calories_resting_kcal', '휴식 칼로리', 'kcal'], ['calories_intake_kcal', '섭취 칼로리', 'kcal'],
  ['sweat_loss_ml', '가민 예상 수분 손실', 'ml'], ['fluid_intake_ml', '섭취 수분', 'ml'], ['body_battery_delta', '바디 배터리 순 영향', '점'],
  ['grade_adjusted_pace_sec_km', '평균 경사 조정 페이스', '초/km'], ['running_seconds', '러닝 시간', '초'], ['walking_seconds', '걷기 시간', '초'], ['idle_seconds', '대기 시간', '초'],
  ['intensity_moderate_min', '중강도 운동 시간', '분'], ['intensity_vigorous_min', '고강도 운동 시간', '분'],
];
const evidenceLabels: Record<string, string> = { distance_km: '거리 km', pace_variability_pct: '페이스 변동 %', heart_rate_drift_pct: '후반 심박/속도 변화 %', rpe: '체감 강도 /10', training_type: '훈련 종류', coverage: '심박 기록 비율', timing_complete: '시간 데이터 완전성', first_split: '첫 1km 페이스 초/km', last_split: '마지막 1km 페이스 초/km', valid_runs_28d: '최근 28일 유효 훈련 횟수', distance_7d_km: '최근 7일 거리 km', eligible_quality: '최근 훈련 기반 충족' };
const kinds = { unspecified: '미지정', easy: '이지런', interval: '인터벌', tempo: '템포런', steady: '지속주', lsd: 'LSD', race: '레이스' };
const graphFields = [
  ['heart_rate_bpm', '심박수', 'bpm', '#d45454'], ['elevation_m', '고도', 'm', '#356856'],
  ['cadence_spm', '달리기 케이던스', 'spm', '#c68c31'], ['power_w', '파워', 'W', '#8161c5'],
  ['stride_length_m', '보폭', 'm', '#297ab9'], ['vertical_ratio_pct', '수직 비율', '%', '#30a587'],
  ['vertical_oscillation_cm', '수직 진동', 'cm', '#8f73b3'], ['ground_contact_ms', '지면 접촉 시간', 'ms', '#c57846'],
  ['performance_condition', '운동 성과', '점', '#307fc2'], ['temperature_c', '센서 온도', '°C', '#b26554'],
];

function MetricCharts({ analysis }: { analysis: Analysis }) {
  const [axis, setAxis] = useState('time');
  const [display, setDisplay] = useState('pace');
  const [index, setIndex] = useState<number | null>(null);
  const field = axis === 'time' ? 'elapsed_seconds' : 'distance_km';
  const extent = Math.max(.001, ...analysis.series.map(p => typeof p[field] === 'number' ? Number(p[field]) : 0));
  const selected = index == null ? null : analysis.series[index];
  const x = (p: Analysis['series'][number]) => Number(p[field] || 0) / extent * 600;
  const fields = [[display === 'pace' ? 'pace_sec_km' : 'speed_kmh', display === 'pace' ? '페이스' : '속도', display === 'pace' ? '/km' : 'km/h', '#4b99d2'], ...graphFields];
  const format = (key: string, value: number | null) => key === 'pace_sec_km' ? pace(value) : number(value, 2);
  return <section className="signal-charts"><div className="chart-controls"><h3>시간·거리별 측정 지표</h3><label>가로축<select aria-label="그래프 가로축" value={axis} onChange={e => { setAxis(e.target.value); setIndex(null); }}><option value="time">시간</option><option value="distance">거리</option></select></label><label>페이스 / 속도<select aria-label="페이스 또는 속도" value={display} onChange={e => setDisplay(e.target.value)}><option value="pace">페이스</option><option value="speed">속도</option></select></label></div>
    <p className="fine">그래프 위를 움직이거나 터치하면 같은 시점의 지표를 함께 확인합니다. 결측·분리 구간은 연결하지 않습니다.</p>
    {fields.map(([key, title, unit, color]) => {
      const valid = analysis.series.filter(p => typeof p[key] === 'number');
      if (valid.length < 2) return <div className="signal-empty" key={key}><strong>{title}</strong><span>시계열 데이터 없음</span></div>;
      const values = valid.map(p => Number(p[key]));
      const low = Math.min(...values), high = Math.max(...values);
      const avg = values.reduce((a, b) => a + b, 0) / values.length;
      const y = (value: number) => key === 'pace_sec_km' ? 15 + (value - low) / Math.max(.01, high - low) * 70 : 85 - (value - low) / Math.max(.01, high - low) * 70;
      const groups: Analysis['series'][] = [[]];
      for (const p of analysis.series) {
        if (p.segment_break || typeof p[key] !== 'number' || p[field] == null) { if (groups.at(-1)!.length) groups.push([]); }
        else groups.at(-1)!.push(p);
      }
      const move = (clientX: number, element: SVGSVGElement) => {
        const bounds = element.getBoundingClientRect();
        const target = Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width)) * extent;
        let found = -1, delta = Infinity;
        analysis.series.forEach((p, i) => { if (typeof p[field] === 'number' && Math.abs(Number(p[field]) - target) < delta) { delta = Math.abs(Number(p[field]) - target); found = i; } });
        setIndex(found >= 0 ? found : null);
      };
      return <div className="signal-chart" key={key}><div className="section-heading"><h4><i style={{ background: color }} />{title}</h4><span>{selected ? format(key, typeof selected[key] === 'number' ? Number(selected[key]) : null) : `${format(key, low)} – ${format(key, high)}`} {unit}</span></div>
        <svg viewBox="0 0 600 105" role="img" aria-label={`${title} 실제 기록 그래프`} onPointerMove={e => move(e.clientX, e.currentTarget)} onPointerDown={e => move(e.clientX, e.currentTarget)}>
          <line x1="0" y1="100" x2="600" y2="100" stroke="#dfe6dc" /><line x1="0" y1={y(avg)} x2="600" y2={y(avg)} stroke={color} strokeDasharray="4 4" opacity=".4" />
          {groups.map((group, i) => <polyline key={i} points={group.map(p => `${x(p)},${y(Number(p[key]))}`).join(' ')} fill="none" stroke={color} strokeWidth="2" />)}
          {selected && <line x1={x(selected)} x2={x(selected)} y1="0" y2="100" stroke="#243d34" strokeDasharray="3 3" />}
        </svg><div className="row muted"><span>0</span><span>{selected ? (axis === 'time' ? clock(Number(selected[field])) : `${number(Number(selected[field]), 3)} km`) : axis === 'time' ? clock(extent) : `${number(extent, 2)} km`}</span></div></div>;
    })}
  </section>;
}

function PrivateRoute({ run }: { run: Run }) {
  const [route, setRoute] = useState<{ segments: { lat: number; lon: number }[][] } | null>(null);
  const [error, setError] = useState('');
  const points = route?.segments.flat() || [];
  const minLat = points.length ? Math.min(...points.map(p => p.lat)) : 0;
  const maxLat = points.length ? Math.max(...points.map(p => p.lat)) : 1;
  const minLon = points.length ? Math.min(...points.map(p => p.lon)) : 0;
  const maxLon = points.length ? Math.max(...points.map(p => p.lon)) : 1;
  const scale = Math.max(maxLon - minLon, maxLat - minLat, .00001);
  return <section className="private-route"><button className="button" onClick={async () => { try { setError(''); setRoute(await api(`/runs/${run.id}/route`)); } catch (e) { setError(e instanceof Error ? e.message : '경로 조회 실패'); } }}>나만 보는 러닝 경로</button><p className="fine">좌표는 본인에게만 제공하며 외부 지도 서버로 보내지 않습니다. 경로 개요이며 배경 지도는 표시하지 않습니다.</p>{error && <p role="alert">{error}</p>}
    {route && (points.length > 1 ? <svg viewBox="0 0 600 240" role="img" aria-label="비공개 러닝 경로">{route.segments.map((s, i) => <polyline key={i} fill="none" stroke="#356856" strokeWidth="3" points={s.map(p => `${20 + (p.lon - minLon) / scale * 200},${220 - (p.lat - minLat) / scale * 200}`).join(' ')} />)}</svg> : <p>원본에 GPS 경로가 없습니다.</p>)}
  </section>;
}

export function RunAnalysis({ run, onRefresh }: { run: Run; onRefresh: () => Promise<void> }) {
  const a = run.analysis!;
  const [report, setReport] = useState<Feedback | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => { let active = true; setReport(null); api<Feedback>(`/runs/${run.id}/feedback`).then(r => { if (active) setReport(r); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [run.id, run.workout_notes, a.engine_version]);
  const device = a.device_summary || {};
  const extra = run.workout_notes?.garmin || {};
  const rows: [string, number | null | undefined, string, string][] = [
    ['경과 시간', a.elapsed_seconds == null ? null : a.elapsed_seconds / 60, '분', '계산'], ['이동 시간', a.moving_seconds == null ? null : a.moving_seconds / 60, '분', '계산'],
    ['정지·구간 공백', a.elapsed_seconds != null && a.moving_seconds != null ? Math.max(0, a.elapsed_seconds - a.moving_seconds) / 60 : null, '분', '계산'],
    ['전체 평균 페이스', a.elapsed_seconds && a.distance_km ? a.elapsed_seconds / a.distance_km : null, '/km', '계산'],
    ['최고심박', a.max_heart_rate, 'bpm', '측정'], ['최저 고도', a.min_elevation_m, 'm', '측정'], ['최고 고도', a.max_elevation_m, 'm', '측정'], ['총 하강', a.descent_m, 'm', '계산'],
    ['빠른 유지 페이스 (10초 이상)', a.best_pace_sec_km, '/km', '계산'],
    ...Object.values(a.metrics || {}).map(m => [`평균 ${m.label}`, m.avg, m.unit, m.source === 'unavailable' ? '미측정' : m.source === 'device_summary' ? 'FIT 요약' : '측정'] as [string, number | null, string, string]),
  ];
  const vendor: [string, string, string][] = [['거리', 'distance_km', 'km'], ['경과 시간', 'elapsed_seconds', '초'], ['타이머 시간', 'timer_seconds', '초'], ['평균 페이스', 'avg_pace_sec_km', '/km'], ['평균 파워', 'avg_power_w', 'W'], ['최대 파워', 'max_power_w', 'W'], ['정규화 파워', 'normalized_power_w', 'W'], ['기기 칼로리', 'calories_kcal', 'kcal'], ['유산소 운동 효과', 'aerobic_training_effect', '점'], ['무산소 운동 효과', 'anaerobic_training_effect', '점'], ['운동 부하', 'training_load', '점']];
  return <div className="run-details">
    <section className="coach-report"><div className="section-heading"><h3>AI 코치 피드백</h3><span className="pill">기록 기반 · 규칙 엔진</span></div><p className="fine">수치 분석과 해설은 분리됩니다. 개인 기록과 훈련 의도를 근거로 작성하며 외부 LLM 없이 작동합니다.</p>
      {report ? <><div className="coach-columns">{[['잘된 점', report.strengths], ['확인할 점 · 부족한 부분', report.opportunities], ['앞으로 할 훈련', report.next_steps]].map(([title, items]) => <div key={String(title)}><h4>{String(title)}</h4><ul>{(items as Feedback['strengths']).map((item, i) => <li key={i}>{item.text}{Object.keys(item.evidence).length > 0 && <details><summary>분석 근거</summary><ul>{Object.entries(item.evidence).map(([key, value]) => <li key={key}>{evidenceLabels[key] || key}: {typeof value === "boolean" ? value ? "충족" : "부족" : String(value)}</li>)}</ul></details>}</li>)}</ul></div>)}</div><p className="fine">{report.limitations.join(' ')}</p></> : <p>코칭을 불러오는 중입니다.</p>}
      <form className="workout-notes" key={`${run.id}-${run.workout_notes?.training_type}`} onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); setSaving(true); try { await api(`/runs/${run.id}/notes`, { method: 'PATCH', body: jsonBody({ training_type: f.get('training_type'), rpe: f.get('rpe') ? Number(f.get('rpe')) : null, note: f.get('note'), garmin: Object.fromEntries(extraFields.map(([key, , unit]) => [key, f.get('garmin_' + key) ? unit === 'text' ? String(f.get('garmin_' + key)) : Number(f.get('garmin_' + key)) : null])) }) }); await onRefresh(); } catch (e) { setError(e instanceof Error ? e.message : '저장 실패'); } finally { setSaving(false); } }}>
        <label>훈련 의도<select aria-label="훈련 의도" name="training_type" defaultValue={run.workout_notes?.training_type || 'unspecified'}>{Object.entries(kinds).map(([value, title]) => <option value={value} key={value}>{title}</option>)}</select></label><label>체감 강도 RPE (1–10)<input name="rpe" type="number" min="1" max="10" defaultValue={run.workout_notes?.rpe ?? ''} /></label><label>훈련 메모<input name="note" maxLength={2000} defaultValue={run.workout_notes?.note || ''} /></label><details className="garmin-extra-form"><summary>가민 추가 정보 직접 기록</summary><p className="fine">FIT에 없는 값을 가민 화면에서 직접 옮길 수 있습니다. 직접 기록한 값으로 표시하며 앱이 추정하지 않습니다.</p><div className="form-grid">{extraFields.map(([key, label, unit]) => <label key={key}>{label}{unit === "text" ? "" : ` (${unit})`}<input name={"garmin_" + key} type={unit === "text" ? "text" : "number"} step={key === "body_battery_delta" ? "1" : "any"} defaultValue={extra[key] ?? ""} maxLength={80} /></label>)}</div></details><button className="button" disabled={saving}>훈련 의도 저장 · 코칭 갱신</button>
      </form>{error && <p role="alert" className="error">{error}</p>}
    </section>
    <section><h3>상세 통계</h3><div className="stat-grid">{rows.map(([label, value, unit, source]) => <div className="stat-item" key={label}><small>{label}</small><strong>{unit === '/km' ? pace(value) : number(value, 2)} {value == null ? '' : unit}</strong><span>{source}</span></div>)}</div></section>
    <section><h3>가민 / 기기 원본 요약</h3><p className="fine">FIT에 실제 저장된 값만 표시합니다. 기기 알고리즘과 PACE 계산 결과는 다를 수 있습니다. GPX에는 대부분 포함되지 않습니다.</p><div className="stat-grid">{vendor.map(([label, key, unit]) => <div className="stat-item" key={key}><small>{label}</small><strong>{unit === '/km' ? pace(typeof device[key] === 'number' ? Number(device[key]) : null) : number(typeof device[key] === 'number' ? Number(device[key]) : null, 2)} {device[key] == null ? '' : unit}</strong><span>FIT 원본</span></div>)}</div><p className="fine">경사 조정 페이스·바디 배터리·수분 손실·기본 운동 효과 분류는 원본에서 확보하지 못해 표시하지 않습니다.</p></section>
    <section><h3>가민 추가 정보</h3><div className="stat-grid">{extraFields.map(([key, label, unit]) => <div className="stat-item" key={key}><small>{label}</small><strong>{extra[key] == null ? "데이터 없음" : unit === "text" ? String(extra[key]) : unit === "초/km" ? pace(Number(extra[key])) : unit === "초" ? clock(Number(extra[key])) : `${number(Number(extra[key]))} ${unit}`}</strong><span>{extra[key] == null ? "원본 미포함 · 직접 기록 가능" : "직접 기록 · 기기 원본과 별도"}</span></div>)}</div></section><PrivateRoute run={run} />
    <MetricCharts analysis={a} />
    <section><h3>심박 영역 시간</h3>{report?.heart_rate_zones.available ? <><p>{report.heart_rate_zones.basis}</p>{report.heart_rate_zones.zones?.map(z => <div className="zone-row" key={z.zone}><span>Z{z.zone} · {z.low_bpm}–{z.high_bpm} bpm</span><progress value={z.seconds} max={Math.max(1, report.heart_rate_zones.covered_seconds || 1)} /><strong>{clock(z.seconds)}</strong></div>)}<p className="fine">심박 결측 시간은 제외합니다. 50% 미만 {clock(report.heart_rate_zones.below_seconds)} · 설정한 최대심박 초과 {clock(report.heart_rate_zones.above_seconds)}</p></> : <p>{report?.heart_rate_zones.reason || '설정에서 최대심박을 입력하고 필요하면 기존 기록을 재분석하세요.'}</p>}</section>
    <section><h3>구간별 페이스</h3><div className="table-wrap"><table><thead><tr><th>구간</th><th>거리</th><th>이동 페이스</th></tr></thead><tbody>{a.splits.map(s => <tr key={s.index}><td>{s.index}{s.partial && <span className="muted"> · 부분</span>}</td><td>{number(s.distance_km, 3)} km</td><td>{pace(s.pace_sec_km)} /km</td></tr>)}</tbody></table></div></section>
    <section><h3>기기 랩</h3>{a.laps?.length ? <div className="table-wrap"><table><thead><tr><th>랩</th><th>거리</th><th>시간</th><th>페이스</th><th>심박</th></tr></thead><tbody>{a.laps.map(l => <tr key={l.index}><td>{l.index}</td><td>{number(l.distance_km, 3)} km</td><td>{clock(l.duration_seconds)}</td><td>{pace(l.pace_sec_km)} /km</td><td>{number(l.avg_heart_rate)} bpm</td></tr>)}</tbody></table></div> : <p>기기 랩 데이터 없음 · GPX의 1km 구간은 위 표에 별도로 계산합니다.</p>}</section>
    {a.warnings.length > 0 && <div className="notice warning"><ul>{a.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
    {a.engine_version !== '1.1.0' && <button className="button" disabled={saving} onClick={async () => { setSaving(true); try { await api(`/runs/${run.id}/reanalyze`, { method: 'POST' }); await onRefresh(); } catch (e) { setError(e instanceof Error ? e.message : '재분석 실패'); } finally { setSaving(false); } }}>기존 원본으로 상세 지표 재분석</button>}
  </div>;
}
