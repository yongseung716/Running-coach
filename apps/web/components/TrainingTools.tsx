"use client";
import { useEffect, useRef, useState } from 'react';
import { api, jsonBody, pace } from '@/lib/api';
import type { Plan, Profile, Run, Target, TrainingCatalog, TrainingDay, WorkoutType } from '@/lib/types';

export const workoutTitles = { rest: '회복', easy: '이지런', interval: '인터벌', tempo: '템포런', steady: '지속주', lsd: 'LSD' };
export function targetLabel(t?: Target) {
  if (!t) return '목표 범위 미설정';
  if (t.mode === 'pace') return `${pace(t.pace_low_sec_km)}–${pace(t.pace_high_sec_km)} /km`;
  if (t.mode === 'hr') return `${t.hr_low}–${t.hr_high} bpm`;
  return `체감 강도 RPE ${t.rpe_low}–${t.rpe_high}/10`;
}
const paceInput = (v?: number | null) => v == null ? '' : `${Math.floor(Math.round(v) / 60)}:${String(Math.round(v) % 60).padStart(2, '0')}`;
const parsePace = (value: FormDataEntryValue | null) => {
  if (!value) return null;
  const match = String(value).match(/^(\d{1,2}):([0-5]\d)$/);
  if (!match) throw new Error('페이스는 5:30처럼 분:초로 입력하세요.');
  return Number(match[1]) * 60 + Number(match[2]);
};

export function AthleteForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const s = profile.athlete_settings || {};
  return <section className="athlete-settings"><h2>나의 훈련 기준</h2><p className="muted">실제 5K/10K 기록과 최근 러닝으로 목표 범위를 계산합니다. 목표 기록과 실제 경기 기록을 구분해서 입력하세요.</p>
    <form className="profile-form" onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); const numeric = (key: string) => f.get(key) ? Number(f.get(key)) : null; setBusy(true); setMessage(''); try { const p = await api<Profile>('/profile/athlete-settings', { method: 'PATCH', body: jsonBody({ hr_max: numeric('hr_max'), lthr: numeric('lthr'), benchmark_5k_min: numeric('benchmark_5k_min'), benchmark_10k_min: numeric('benchmark_10k_min'), benchmark_5k_date: f.get('benchmark_5k_date') || null, benchmark_10k_date: f.get('benchmark_10k_date') || null }) }); onSaved(p); setMessage('훈련 기준을 저장했습니다. 훈련 편집에서 새 추천 범위를 확인하세요.'); } catch (e) { setMessage(e instanceof Error ? e.message : '저장 실패'); } finally { setBusy(false); } }}>
      <label>설정할 최대심박 (bpm)<input name="hr_max" type="number" min="100" max="240" defaultValue={s.hr_max ?? ''} placeholder="알고 있는 측정·설정값" /></label>
      <label>설정할 역치심박 (bpm, 선택)<input name="lthr" type="number" min="90" max="220" defaultValue={s.lthr ?? ''} /></label>
      <label>실제 5K 기록 (분)<input name="benchmark_5k_min" type="number" min="10.01" max="150" step="0.01" defaultValue={s.benchmark_5k_min ?? ''} placeholder="예: 25.5 = 25분 30초" /></label>
      <label>5K 기록 날짜<input name="benchmark_5k_date" type="date" max={new Date().toISOString().slice(0, 10)} defaultValue={s.benchmark_5k_date || s.benchmark_date || ''} /></label>
      <label>실제 10K 기록 (분)<input name="benchmark_10k_min" type="number" min="20.01" max="300" step="0.01" defaultValue={s.benchmark_10k_min ?? ''} /></label>
      <label>10K 기록 날짜<input name="benchmark_10k_date" type="date" max={new Date().toISOString().slice(0, 10)} defaultValue={s.benchmark_10k_date || s.benchmark_date || ''} /></label>
      <button className="button primary" disabled={busy}>훈련 기준 저장</button>
    </form>{message && <p role="status">{message}</p>}<p className="fine">최고 관측 심박과 나이 공식으로 최대심박을 자동 설정하지 않습니다. 180일이 지난 경기 기록은 자동 페이스 근거에서 제외합니다. 두 경기 기록이 다르면 보수적인 범위를 선택합니다.</p>
  </section>;
}

function WorkoutEditor({ plan, day, onClose, onSaved }: { plan: Plan; day: TrainingDay; onClose: () => void; onSaved: () => Promise<void> }) {
  const [data, setData] = useState<TrainingCatalog | null>(null);
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const elements = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]') || []);
    elements()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key === 'Tab') {
        const all = elements(), first = all[0], last = all.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
  }, [onClose]);

  const [type, setType] = useState<WorkoutType>(day.type);
  const [mode, setMode] = useState<'pace' | 'hr' | 'rpe'>(day.target?.mode || 'rpe');
  const [volume, setVolume] = useState(day.distance_km == null ? 'time' : 'distance');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [repetitions, setRepetitions] = useState(Number(day.workout_spec?.repetitions || 4));
  const [meters, setMeters] = useState(Number(day.workout_spec?.repeat_distance_m || 400));
  const [recovery, setRecovery] = useState(Number(day.workout_spec?.recovery_distance_m ?? 200));
  const [warmup, setWarmup] = useState(Number(day.workout_spec?.warmup_km ?? 1));
  const [cooldown, setCooldown] = useState(Number(day.workout_spec?.cooldown_km ?? 1));
  useEffect(() => { let active = true; api<TrainingCatalog>('/training/catalog').then(v => { if (active) setData(v); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, []);
  const [suggestion, setSuggestion] = useState(0);
  const recommended = type === 'interval' ? data?.interval_targets[String(meters)] || data?.types.find(t => t.type === type)?.target : data?.types.find(t => t.type === type)?.target;
  const target = suggestion === 0 && type === day.type && day.target && (type !== 'interval' || meters === Number(day.workout_spec?.repeat_distance_m || 400)) ? day.target : recommended;
  return <div className="editor-backdrop"><section ref={dialog} className="workout-editor" role="dialog" aria-modal="true" aria-labelledby="workout-editor-title"><div className="section-heading"><h3 id="workout-editor-title">{['월', '화', '수', '목', '금', '토', '일'][day.day_index]}요일 훈련 편집</h3><button className="text-button" onClick={onClose}>닫기</button></div>
    {data && <div className="notice"><div><strong>{data.reference.source}</strong><p>추천 신뢰도: {data.reference.confidence === 'moderate' ? '실제 기록 기반' : data.reference.confidence === 'low' ? '낮음 · 참고 범위' : '근거 부족'}</p>{!data.reference.eligible_quality && <p>고강도 자동 추천에 필요한 최근 훈련 기반이 부족합니다.</p>}</div></div>}
    <form onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); const n = (key: string) => f.get(key) ? Number(f.get(key)) : null; setBusy(true); setError(''); try { const body = { type, mode, distance_km: type !== 'interval' && type !== 'rest' && volume === 'distance' ? n('distance_km') : null, duration_min: type !== 'interval' && type !== 'rest' && volume === 'time' ? n('duration_min') : null, repetitions, repeat_distance_m: meters, recovery_distance_m: recovery, warmup_km: warmup, cooldown_km: cooldown, pace_low_sec_km: mode === 'pace' ? parsePace(f.get('pace_low')) : null, pace_high_sec_km: mode === 'pace' ? parsePace(f.get('pace_high')) : null, hr_low: mode === 'hr' ? n('hr_low') : null, hr_high: mode === 'hr' ? n('hr_high') : null }; await api(`/plans/${plan.id}/days/${day.day_index}`, { method: 'PATCH', body: jsonBody(body) }); await onSaved(); onClose(); } catch (e) { setError(e instanceof Error ? e.message : '편집 실패'); } finally { setBusy(false); } }}>
      <label>훈련 종류<select aria-label="편집 훈련 종류" value={type} onChange={e => { const kind = e.target.value as WorkoutType; setType(kind); const t = data?.types.find(t => t.type === kind)?.target; setMode(t?.mode || 'rpe'); }}>{Object.entries(workoutTitles).map(([value, title]) => <option value={value} key={value}>{title}</option>)}</select></label>
      {type === 'interval' ? <><div className="form-grid"><label>반복 거리 (m)<select aria-label="인터벌 반복 거리" value={meters} onChange={e => setMeters(Number(e.target.value))}>{(data?.interval_distances_m || [200, 400, 800, 1000, 1600, 2000]).map(m => <option key={m} value={m}>{m} m</option>)}</select></label><label>반복 횟수<input aria-label="인터벌 반복 횟수" type="number" min="1" max="20" value={repetitions} onChange={e => setRepetitions(Number(e.target.value))} /></label><label>회복 거리 (m)<input type="number" min="0" max="5000" value={recovery} onChange={e => setRecovery(Number(e.target.value))} /></label><label>워밍업 (km)<input type="number" min="0" max="10" step=".1" value={warmup} onChange={e => setWarmup(Number(e.target.value))} /></label><label>쿨다운 (km)<input type="number" min="0" max="10" step=".1" value={cooldown} onChange={e => setCooldown(Number(e.target.value))} /></label></div><p className="notice">본훈련 {repetitions} × {meters}m · 회복 포함 총 {(warmup + cooldown + (repetitions * meters + Math.max(0, repetitions - 1) * recovery) / 1000).toFixed(2)}km</p></> : type !== 'rest' ? <div className="form-grid"><label>거리 / 시간<select aria-label="훈련 거리 또는 시간" value={volume} onChange={e => setVolume(e.target.value)}><option value="distance">거리</option><option value="time">시간</option></select></label>{volume === 'distance' ? <label>훈련 거리 (km)<input name="distance_km" type="number" min=".1" max="100" step=".1" defaultValue={day.distance_km || 3} required /></label> : <label>훈련 시간 (분)<input name="duration_min" type="number" min="1" max="600" defaultValue={day.duration_min || 20} required /></label>}</div> : null}
      {type !== 'rest' && <><label>목표 기준<select aria-label="목표 기준" value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="pace">페이스 / km</option><option value="hr">심박 bpm</option><option value="rpe">체감 강도 RPE</option></select></label><button type="button" className="text-button" onClick={() => { setSuggestion(v => v + 1); }}>자동 추천 범위 적용</button><p className="fine">자동 추천: {targetLabel(recommended ? { ...recommended, mode } : undefined)} · {recommended?.basis}</p><div className="form-grid" key={`${type}-${mode}-${meters}-${suggestion}`}>{mode === 'pace' ? <><label>목표 페이스 빠른 쪽<input name="pace_low" placeholder="5:00" defaultValue={paceInput(target?.pace_low_sec_km)} /></label><label>목표 페이스 느린 쪽<input name="pace_high" placeholder="5:30" defaultValue={paceInput(target?.pace_high_sec_km)} /></label></> : mode === 'hr' ? <><label>목표 심박 낮은 쪽<input name="hr_low" type="number" min="30" max="240" defaultValue={target?.hr_low ?? ''} /></label><label>목표 심박 높은 쪽<input name="hr_high" type="number" min="30" max="240" defaultValue={target?.hr_high ?? ''} /></label></> : <p>{targetLabel(recommended)}</p>}</div></>}
      {type === 'tempo' && <p className="fine">표시한 거리·시간은 본훈련입니다. 워밍업과 쿨다운은 각각 10분씩 추가됩니다.</p>}
      {error && <p role="alert" className="error">{error}</p>}<button className="button primary" disabled={busy || !data}>훈련 저장</button>
    </form><details><summary>추천 방법과 제한</summary><ul>{data?.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
  </section></div>;
}

export function PlanDays({ plan, runs, onRefresh }: { plan: Plan; runs: Run[]; onRefresh: () => Promise<void> }) {
  const [editing, setEditing] = useState<TrainingDay | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <><div className="plan-days">{plan.prescription.days.map(day => {
    const done = plan.completions.some(c => c.day_index === day.day_index);
    return <article className={`plan-day ${day.type === 'rest' ? 'rest' : ''} ${done ? 'done' : ''}`} key={day.day_index}><div className="day-date"><strong>{['월', '화', '수', '목', '금', '토', '일'][day.day_index]}</strong><span>{day.date.slice(5).replace('-', '월 ')}일</span></div><div className="day-body"><span className="pill">{workoutTitles[day.type]}</span><h3>{day.title} <span>{day.distance_km != null ? `${day.distance_km} km` : day.duration_min != null ? `${day.duration_min}분` : ''}</span></h3><p>{day.instruction}</p>{day.type !== 'rest' && <strong className="target-range">{targetLabel(day.target)}</strong>}
      {!!day.steps?.length && <details><summary>훈련 단계 보기</summary><ol>{day.steps.map((step, i) => <li key={i}>{step.title} · {step.distance_km != null ? `${step.distance_km}km` : step.duration_min ? `${step.duration_min}분` : ''} · {targetLabel(step.target)}</li>)}</ol></details>}
      {day.warnings?.map(w => <p className="warning-text" key={w}>{w}</p>)}<button className="text-button" disabled={done || busy} onClick={() => setEditing(day)}>훈련 편집</button></div>
      {day.type !== 'rest' && <form onSubmit={async e => { e.preventDefault(); const runId = new FormData(e.currentTarget).get('run_id'); setBusy(true); try { await api(`/plans/${plan.id}/days/${day.day_index}/completion`, { method: done ? 'DELETE' : 'PUT', ...(done ? {} : { body: jsonBody({ run_id: runId || null }) }) }); await onRefresh(); } catch (e) { setError(e instanceof Error ? e.message : '완료 기록 실패'); } finally { setBusy(false); } }}><select name="run_id" aria-label={`${day.title}에 연결할 기록`} disabled={done || busy}><option value="">직접 완료 기록</option>{runs.filter(r => r.status === 'completed').map(r => <option key={r.id} value={r.id}>{r.analysis?.started_at?.slice(0, 10)} · {r.analysis?.distance_km}km</option>)}</select><button className={`button ${done ? 'completed' : ''}`} disabled={busy}>{done ? '완료 취소' : '완료 기록'}</button></form>}
    </article>;
  })}</div>{plan.prescription.editing_warnings?.map(w => <p className="notice warning" key={w}>{w}</p>)}{error && <p role="alert">{error}</p>}{editing && <WorkoutEditor plan={plan} day={editing} onClose={() => setEditing(null)} onSaved={onRefresh} />}</>;
}
