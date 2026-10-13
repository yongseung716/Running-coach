"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Activity, ArrowDownToLine, ArrowRight, Check, ChevronRight, CircleHelp, FileUp, Flag, Footprints, Heart, LayoutDashboard, LogOut, Mountain, Plus, Settings, ShieldCheck, Timer, Trash2, Users, X } from "lucide-react";
import { RunAnalysis } from "@/components/RunAnalysis";
import { AthleteForm, PlanDays } from "@/components/TrainingTools";
import { api, ApiError, jsonBody, pace } from "@/lib/api";
import type { Analysis, Crew, CrewDetail, CrewSummary, Dashboard, Plan, Profile, Run, RunPage } from "@/lib/types";

type Tab = "overview" | "runs" | "plan" | "crews" | "settings";
type InstallPrompt = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> };
const links = [
  { id: "overview" as const, title: "대시보드", icon: LayoutDashboard },
  { id: "runs" as const, title: "러닝 기록", icon: Activity },
  { id: "plan" as const, title: "훈련 계획", icon: Flag },
  { id: "crews" as const, title: "나의 크루", icon: Users },
  { id: "settings" as const, title: "설정", icon: Settings },
];
const statuses = { queued: "분석 대기", processing: "분석 중", completed: "분석 완료", failed: "분석 실패" };
const fmt = (value: number | null | undefined, digits = 1) => value == null ? "—" : value.toLocaleString("ko-KR", { maximumFractionDigits: digits });
const shortDate = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString("ko-KR", { month: "short", day: "numeric", timeZone: "UTC" }) : "날짜 없음";

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}
function Empty({ title, text }: { title: string; text: string }) {
  return <div className="empty"><Footprints size={28} aria-hidden="true" /><h3>{title}</h3><p>{text}</p></div>;
}
function Metric({ label, value, unit, icon }: { label: string; value: string; unit: string; icon: ReactNode }) {
  return <Card className="metric"><div className="metric-label">{label}{icon}</div><div className="metric-value">{value}<span>{unit}</span></div></Card>;
}

export default function Home() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("overview");
  const [runs, setRuns] = useState<Run[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [crews, setCrews] = useState<Crew[]>([]);
  const [crewId, setCrewId] = useState("");
  const [crewDetail, setCrewDetail] = useState<CrewDetail | null>(null);
  const [crewSummary, setCrewSummary] = useState<CrewSummary | null>(null);
  const [inviteCode, setInviteCode] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ message: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [signup, setSignup] = useState(false);
  const [mode, setMode] = useState<string>("");
  const [install, setInstall] = useState<InstallPrompt | null>(null);
  const [offline, setOffline] = useState(false);
  const selected = runs.find(r => r.id === selectedId);
  const plan = plans[0];
  const crew = crews.find(c => c.id === crewId);
  const isManager = crew?.membership.role === "owner" || crew?.membership.role === "admin";

  const refreshData = useCallback(async () => {
    const [r, d, p, c] = await Promise.all([api<RunPage>("/runs"), api<Dashboard>("/dashboard"), api<Plan[]>("/plans"), api<Crew[]>("/crews")]);
    setRuns(r.items); setCursor(r.next_cursor); setDashboard(d); setPlans(p); setCrews(c);
  }, []);
  const refreshCrew = useCallback(async (id: string) => {
    const [detail, summary] = await Promise.all([api<CrewDetail>(`/crews/${id}`), api<CrewSummary>(`/crews/${id}/summary`)]);
    setCrewDetail(detail); setCrewSummary(summary);
  }, []);
  const action = async (work: () => Promise<void>) => {
    setBusy(true); setFlash(null);
    try { await work(); }
    catch (error) { setFlash({ message: error instanceof Error ? error.message : "요청에 실패했습니다.", error: true }); }
    finally { setBusy(false); }
  };
  const message = (text: string) => setFlash({ message: text, error: false });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const p = await api<Profile>("/profile");
        if (active) { setProfile(p); await refreshData(); }
      } catch (error) {
        if (active && !(error instanceof ApiError && error.status === 401)) setFlash({ message: error instanceof Error ? error.message : "연결 실패", error: true });
      } finally { if (active) setLoading(false); }
    })();
    api<{ mode: string }>("/health").then(h => { if (active) setMode(h.mode); }).catch(() => {});
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") navigator.serviceWorker.register("/sw.js").catch(() => {});
    const prompt = (event: Event) => { event.preventDefault(); setInstall(event as InstallPrompt); };
    const online = () => setOffline(!navigator.onLine);
    online(); window.addEventListener("beforeinstallprompt", prompt); window.addEventListener("online", online); window.addEventListener("offline", online);
    return () => { active = false; window.removeEventListener("beforeinstallprompt", prompt); window.removeEventListener("online", online); window.removeEventListener("offline", online); };
  }, [refreshData]);
  useEffect(() => {
    if (!profile || !runs.some(r => r.status === "queued" || r.status === "processing")) return;
    const timer = window.setInterval(() => {
      Promise.all([api<RunPage>("/runs"), api<Dashboard>("/dashboard")]).then(([r, d]) => { setRuns(r.items); setCursor(r.next_cursor); setDashboard(d); }).catch(error => setFlash({ message: error.message, error: true }));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [profile, runs]);
  useEffect(() => {
    if (!crewId || crew?.membership.status !== "active") { setCrewDetail(null); setCrewSummary(null); return; }
    let active = true;
    setCrewDetail(null); setCrewSummary(null); setInviteCode("");
    Promise.all([api<CrewDetail>(`/crews/${crewId}`), api<CrewSummary>(`/crews/${crewId}/summary`)]).then(([detail, summary]) => {
      if (active) { setCrewDetail(detail); setCrewSummary(summary); }
    }).catch(error => { if (active) setFlash({ message: error.message, error: true }); });
    return () => { active = false; };
  }, [crewId, crew?.membership.status]);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await action(async () => {
      const result = await api<{ authenticated?: boolean; message: string }>(signup ? "/auth/signup" : "/auth/login", { method: "POST", body: jsonBody(Object.fromEntries(data)) });
      if (signup && !result.authenticated) { message(result.message); setSignup(false); return; }
      setSignup(false); setProfile(await api<Profile>("/profile")); await refreshData(); message(result.message);
    });
  }
  async function upload(file: File | undefined) {
    if (!file) return;
    await action(async () => {
      if (file.size > 10 * 1024 * 1024) throw new Error("업로드 파일은 10 MiB 이하여야 합니다.");
      const form = new FormData(); form.append("file", file);
      const run = await api<Run>("/runs", { method: "POST", body: form });
      await refreshData(); setSelectedId(run.id); setTab("runs"); message("파일을 접수했습니다. 분석 상태가 자동으로 갱신됩니다.");
    });
  }
  async function download(path: string, filename: string) {
    await action(async () => {
      await api<Profile>("/profile"); // Refresh session before binary download.
      const response = await fetch(`/api${path}`, { cache: "no-store" });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "다운로드 실패" })); throw new Error(error.detail);
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  const uploadButton = <label className={`button primary ${busy ? "disabled" : ""}`}><FileUp size={17} /> GPX · FIT 업로드<input aria-label="GPX 업로드" aria-description="GPX, FIT 또는 FIT 원본 ZIP 파일 업로드" type="file" accept=".gpx,.fit,.zip,application/gpx+xml,application/octet-stream" hidden disabled={busy} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>;

  if (loading) return <main className="loading"><span className="brand">PACE<span>↗</span></span><p>러닝 공간을 준비하고 있습니다…</p></main>;
  if (!profile) return <main className="auth-layout"><section className="auth-story"><a href="/" className="brand">PACE<span>↗</span></a><span className="eyebrow">YOUR PACE. YOUR PROGRESS.</span><h1>당신의 기록에서,<br />다음 달리기로.</h1><p>매일 조금씩 나아지는 러닝.<br />나의 페이스를 이해하고 크루와 함께 이어가세요.</p><div className="auth-lines" aria-hidden="true" /><div className="row"><ShieldCheck size={20} /><span>GPS 원본은 나만 볼 수 있어요.</span></div></section><section className="auth-form"><span className="pill">RUNNING COACH</span><h2>{signup ? "나의 러닝을 시작하세요" : "다시 만나서 반가워요"}</h2><p className="muted">{signup ? "첫 기록부터 꾸준한 훈련까지 함께합니다." : "로그인하고 오늘의 러닝을 준비하세요."}</p>{flash && <div role="alert" className={`notice ${flash.error ? "error" : ""}`}>{flash.message}</div>}<form onSubmit={authenticate}>{signup && <label>이름<input name="display_name" autoComplete="nickname" required maxLength={40} placeholder="크루에서 사용할 이름" /></label>}<label>이메일<input name="email" type="email" autoComplete="email" required placeholder="runner@example.com" /></label><label>비밀번호<input name="password" type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={10} maxLength={128} placeholder="10자 이상" /></label><button className="button primary" disabled={busy}>{busy ? "처리 중…" : signup ? "회원가입" : "로그인"}<ArrowRight size={17} /></button></form><button className="text-button" onClick={() => { setSignup(!signup); setFlash(null); }}>{signup ? "이미 계정이 있나요? 로그인" : "처음 오셨나요? 회원가입"}</button><p className="fine">{mode === "development" || mode === "test" ? "로컬 개발 모드 · 이 환경의 계정은 운영 Supabase 계정과 별개입니다." : "기록은 기본 비공개이며, 크루별 공유 동의를 직접 선택할 수 있습니다."}</p></section></main>;

  return <div className="app-shell"><aside className="sidebar"><a href="/" className="brand">PACE<span>↗</span></a><p className="sidebar-tag">RUNNING COACH</p><nav aria-label="주 메뉴">{links.map(link => <button key={link.id} className={tab === link.id ? "active" : ""} onClick={() => { setTab(link.id); setSelectedId(null); }}><link.icon size={19} />{link.title}{tab === link.id && <span className="nav-dot" />}</button>)}</nav><div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={19} /><p>나의 페이스,<br /><strong>나의 데이터.</strong></p></div><button className="user-card" onClick={() => setTab("settings")}><span className="avatar">{profile.display_name.slice(0, 1)}</span><span><strong>{profile.display_name}</strong><small>개인 러닝 공간</small></span><ChevronRight size={16} /></button></div></aside>
    <div className="content"><header className="topbar"><span className="mobile-brand brand">PACE<span>↗</span></span><span className="breadcrumb">나의 러닝 공간 <ChevronRight size={13} /> {links.find(l => l.id === tab)?.title}</span><div className="row"><span className="today">{new Date().toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short", timeZone: "UTC" })}</span>{install && <button className="button small" onClick={() => action(async () => { await install.prompt(); await install.userChoice; setInstall(null); })}>앱 설치</button>}<span className="avatar small-avatar" aria-label={profile.display_name}>{profile.display_name.slice(0, 1)}</span></div></header>
    <main className="main"><div className="page-heading"><div><span className="eyebrow">KEEP MOVING FORWARD</span><h1>{tab === "overview" ? `${profile.display_name}님, 오늘도 나의 페이스로.` : links.find(l => l.id === tab)?.title}</h1><p>{tab === "overview" ? "기록을 돌아보고, 다음 한 걸음을 준비하세요." : tab === "runs" ? "나의 달리기를 수치로 이해하세요." : tab === "plan" ? "최근 기록을 바탕으로 무리 없이 이어가는 한 주." : tab === "crews" ? "함께 달리되, 공유는 내가 선택해요." : "목표와 데이터 공개 범위를 직접 관리하세요."}</p></div>{tab !== "settings" && tab !== "crews" && uploadButton}</div>
    {mode && mode !== "production" && <div className="dev-note">로컬 개발 모드 · 실제 업로드 파일을 분석합니다. 기본 예시 기록은 없습니다.</div>}
    {offline && <div role="status" className="notice error">오프라인입니다. 연결이 복구되면 다시 시도하세요.</div>}
    {flash && <div role="alert" className={`notice ${flash.error ? "error" : ""}`}><span>{flash.message}</span><button aria-label="알림 닫기" className="icon-button" onClick={() => setFlash(null)}><X size={17} /></button></div>}

    {tab === "overview" && <><div className="hero"><div><span className="eyebrow">SMALL STEPS. REAL PROGRESS.</span><h2>잘 달리는 것보다,<br />오래 달리는 우리.</h2><p>오늘의 기록이 내일의 방향이 됩니다.<br />나만의 훈련 계획을 확인해 보세요.</p><button className="button lime" onClick={() => setTab("plan")}>이번 주 계획 보기 <ArrowRight size={17} /></button></div><div className="contour" aria-hidden="true"><svg viewBox="0 0 500 290">{Array.from({ length: 13 }, (_, i) => <ellipse key={i} cx="300" cy="130" rx={80 + i * 19} ry={30 + i * 14} transform="rotate(-28 300 130)" />)}<path className="route" d="M180 238 C110 172 210 164 230 110 S325 84 365 45" /><circle className="route-start" cx="180" cy="238" r="8" /><circle className="route-end" cx="365" cy="45" r="6" /></svg><span className="hero-caption"><Activity size={16} /> FIND YOUR OWN PACE</span></div></div><div className="metrics"><Metric label="최근 28일 누적 거리" value={fmt(dashboard?.distance_28d_km)} unit="km" icon={<Footprints size={18} />} /><Metric label="최근 28일 러닝" value={fmt(dashboard?.runs_28d, 0)} unit="회" icon={<Activity size={18} />} /><Metric label="이번 주 훈련 목표" value={fmt(plan?.prescription.basis.weekly_target_km)} unit="km" icon={<Flag size={18} />} /></div><div className="dashboard-grid"><Card><div className="section-heading"><div><h2>꾸준함의 기록</h2><p>최근 4주 · 실제 GPX 기록</p></div><span className="pill">주간 거리</span></div>{dashboard && dashboard.weekly.some(w => w.distance_km > 0) ? <div className="bar-chart" role="img" aria-label="최근 4주 주간 거리">{dashboard.weekly.map((w, i) => <div className="bar-column" key={w.week_start}><span>{fmt(w.distance_km)} km</span><div className="bar-track"><div className={`bar ${i === 3 ? "current" : ""}`} style={{ height: `${Math.max(0, w.distance_km / Math.max(...dashboard.weekly.map(v => v.distance_km), 1) * 100)}%` }} /></div><small>{shortDate(w.week_start)}</small></div>)}</div> : <Empty title="첫 기록을 기다리고 있어요" text="GPX를 업로드하면 주간 거리가 여기에 표시됩니다." />}<p className="fine">{dashboard?.note}</p></Card><Card className="coach-card"><div className="section-heading"><h2>나의 러닝 코치</h2><span className="coach-icon"><Activity size={18} /></span></div><span className="eyebrow">RULES BASED COACHING</span><h3>{plan ? "기록을 읽고, 꾸준함을 계획해요." : "첫 계획부터 가볍게 시작해요."}</h3><p>{plan?.prescription.explanation || "훈련 이력이 없으면 15분 달리기·걷기로 시작합니다. 목표보다 현재의 몸 상태를 우선하세요."}</p><button className="text-button" onClick={() => setTab("plan")}>{plan ? "훈련 계획 확인" : "주간 계획 만들기"}<ArrowRight size={16} /></button><div className="coach-foot"><ShieldCheck size={14} /> 수치 계산과 코칭 해설을 분리합니다.</div></Card></div><Card><div className="section-heading"><div><h2>최근 러닝</h2><p>하나씩 쌓이는 나의 발자취</p></div><button className="text-button" onClick={() => setTab("runs")}>전체 보기 <ArrowRight size={16} /></button></div>{runs.length ? <div>{runs.slice(0, 4).map(run => <button className="run-row" key={run.id} onClick={() => { setTab("runs"); setSelectedId(run.id); }}><span className="run-icon"><Footprints size={20} /></span><span className="run-name"><strong>{shortDate(run.analysis?.started_at || run.created_at)} 러닝</strong><small>{statuses[run.status]}</small></span><span><strong>{fmt(run.analysis?.distance_km)} <small>km</small></strong></span><span className="row-pace">{pace(run.analysis?.pace_sec_km)}<small> /km</small></span><ChevronRight size={16} /></button>)}</div> : <Empty title="아직 러닝 기록이 없어요" text="가민에서 FIT 원본을 내보내거나 GPX 기록을 업로드하세요." />}</Card></>}

    {tab === "runs" && <>{selected ? <Card><div className="section-heading"><div><button className="text-button" onClick={() => setSelectedId(null)}>← 기록 목록</button><h2>{shortDate(selected.analysis?.started_at || selected.created_at)} 러닝 분석</h2></div><span className="pill">{statuses[selected.status]}</span></div>{selected.analysis ? <><div className="analysis-metrics"><Metric label="거리" value={fmt(selected.analysis.distance_km, 3)} unit="km" icon={<Footprints size={17} />} /><Metric label="이동 페이스" value={pace(selected.analysis.pace_sec_km)} unit="/km" icon={<Timer size={17} />} /><Metric label="평균 심박" value={fmt(selected.analysis.avg_heart_rate)} unit="bpm" icon={<Heart size={17} />} /><Metric label="누적 상승" value={fmt(selected.analysis.ascent_m)} unit="m" icon={<Mountain size={17} />} /></div><p className="fine">경과 {fmt(selected.analysis.elapsed_seconds == null ? null : selected.analysis.elapsed_seconds / 60)}분 · 이동 {fmt(selected.analysis.moving_seconds == null ? null : selected.analysis.moving_seconds / 60)}분 · 심박 coverage {fmt(selected.analysis.heart_rate_coverage * 100, 0)}% · 분석 v{selected.analysis.engine_version}</p><RunAnalysis run={selected} onRefresh={refreshData} /></> : <Empty title={selected.status === "failed" ? "분석에 실패했어요" : "기록을 분석하고 있어요"} text={selected.error || "처리 상태는 자동으로 갱신됩니다. 오래 대기하면 worker 실행 상태를 확인하세요."} />}<div className="row button-row"><button className="button" disabled={busy} onClick={() => download(`/runs/${selected.id}/file`, `${selected.id}.${selected.file_format || "gpx"}`)}><ArrowDownToLine size={16} /> 원본 다운로드</button><button className="button danger" disabled={busy} onClick={() => { if (window.confirm("원본 GPX와 분석 기록을 영구 삭제할까요?")) action(async () => { await api(`/runs/${selected.id}`, { method: "DELETE" }); setSelectedId(null); await refreshData(); message("원본과 분석 기록을 삭제했습니다."); }); }}><Trash2 size={16} /> 기록 삭제</button></div></Card> : <Card><div className="section-heading"><h2>내 기록 <span className="muted">{runs.length}</span></h2><span className="pill"><ShieldCheck size={13} /> 나만 공개</span></div><label className="upload-zone"><FileUp size={28} /><strong>GPX · FIT 파일로 러닝을 기록하세요</strong><span>최대 10 MiB · FIT 원본 또는 FIT 하나가 든 ZIP도 지원합니다</span><input aria-label="분석할 GPX 파일 선택" type="file" accept=".gpx,.fit,.zip" disabled={busy} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>{runs.map(run => <button className="run-row" key={run.id} onClick={() => setSelectedId(run.id)}><span className="run-icon"><Activity size={20} /></span><span className="run-name"><strong>{shortDate(run.analysis?.started_at || run.created_at)} 러닝</strong><small>{statuses[run.status]}{run.error ? ` · ${run.error}` : ""}</small></span><strong>{fmt(run.analysis?.distance_km)} <small>km</small></strong><ChevronRight size={16} /></button>)}{cursor && <button className="button" disabled={busy} onClick={() => action(async () => { const next = await api<RunPage>(`/runs?cursor=${cursor}`); setRuns(current => [...current, ...next.items]); setCursor(next.next_cursor); })}>이전 기록 더 보기</button>}</Card>}</>}

    {tab === "plan" && <><Card><div className="section-heading"><div><h2>{plan ? `${shortDate(plan.week_start)} 주간 계획` : "나에게 맞는 한 주"}</h2><p>규칙 기반 코칭 · 외부 AI API 없이 작동</p></div><button className="button primary" disabled={busy} onClick={() => action(async () => { await api<Plan>("/plans", { method: "POST" }); await refreshData(); message("이번 주 계획을 준비했습니다. 같은 주의 기존 계획은 유지됩니다."); })}><Plus size={17} /> 이번 주 계획 생성</button></div>{plan ? <><div className="plan-basis"><Activity size={22} /><div><strong>{plan.prescription.explanation}</strong><p>근거: 최근 28일 유효 기록 {plan.prescription.basis.valid_runs_28d}회 · 최근 7일 {fmt(plan.prescription.basis.distance_7d_km)} km · 목표 페이스 {pace(plan.prescription.basis.goal_pace_sec_km)} /km</p></div></div><PlanDays plan={plan} runs={runs} onRefresh={refreshData} /><div className="notice warning"><CircleHelp size={20} /><div><strong>안전하게 이어가는 러닝</strong><ul>{plan.prescription.limitations.map(l => <li key={l}>{l}</li>)}</ul></div></div></> : <Empty title="지금의 나에게 맞춰 시작하세요" text="이번 주 계획 생성을 누르면 최근 훈련 이력과 목표를 사용합니다. 이력이 없으면 짧은 달리기·걷기를 제안합니다." />}</Card>{plans.length > 1 && <Card><h2>이전 계획</h2>{plans.slice(1).map(p => <p key={p.id}>{shortDate(p.week_start)} 주 · {p.completions.length}개 훈련 완료</p>)}</Card>}</>}

    {tab === "crews" && <><div className="two-columns"><Card><h2>크루 만들기</h2><p className="muted">여러 크루를 자유롭게 운영하고 가입하세요.</p><form className="inline-form" onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const name = new FormData(form).get("name"); action(async () => { const c = await api<Crew>("/crews", { method: "POST", body: jsonBody({ name }) }); await refreshData(); setCrewId(c.id); form.reset(); message("크루를 만들었습니다."); }); }}><input name="name" aria-label="새 크루 이름" required maxLength={60} placeholder="크루 이름" /><button className="button primary" disabled={busy}><Plus size={17} /> 만들기</button></form></Card><Card><h2>초대 코드로 가입</h2><p className="muted">가입 요청 후 운영자의 승인을 기다려주세요.</p><form className="inline-form" onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const code = new FormData(form).get("code"); action(async () => { await api("/crews/join", { method: "POST", body: jsonBody({ code }) }); await refreshData(); form.reset(); message("가입 요청을 보냈습니다."); }); }}><input name="code" aria-label="크루 초대 코드" required minLength={10} maxLength={128} placeholder="초대 코드" /><button className="button" disabled={busy}>가입 요청</button></form></Card></div><Card><div className="section-heading"><h2>나의 크루</h2><button className="text-button" disabled={busy} onClick={() => action(refreshData)}>새로고침</button></div>{crews.length ? <div className="crew-list">{crews.map(c => <button key={c.id} className={`crew-button ${crewId === c.id ? "selected" : ""}`} onClick={() => setCrewId(c.id)}><Users size={21} /><strong>{c.name}</strong><span className="pill">{c.membership.status === "active" ? c.membership.role : c.membership.status === "pending" ? "승인 대기" : "가입 거절"}</span></button>)}</div> : <Empty title="함께 달릴 크루를 만나보세요" text="크루를 만들거나 초대 코드로 가입을 요청하세요." />}</Card>{crew && crew.membership.status !== "active" && <Card><h2>{crew.name}</h2><p>{crew.membership.status === "pending" ? "운영자 승인을 기다리고 있습니다." : "가입 요청이 거절되었습니다."}</p><button className="button danger" disabled={busy} onClick={() => action(async () => { await api(`/crews/${crew.id}/membership`, { method: "DELETE" }); setCrewId(""); await refreshData(); })}>가입 내역 제거</button></Card>}{crew && crew.membership.status === "active" && <Card><div className="section-heading"><h2>{crew.name}</h2><span className="pill">최근 28일 · 동의한 회원만</span></div><label className="consent"><input type="checkbox" checked={crew.membership.share_summary} disabled={busy} onChange={e => { const share = e.target.checked; const previous = crew.membership.share_summary; setCrews(current => current.map(c => c.id === crew.id ? { ...c, membership: { ...c.membership, share_summary: share } } : c)); action(async () => { try { await api(`/crews/${crew.id}/consent`, { method: "PATCH", body: jsonBody({ share_summary: share }) }); await refreshData(); await refreshCrew(crew.id); message(share ? "이 크루에 최근 훈련 요약 공유를 동의했습니다." : "공유 동의를 철회했습니다."); } catch (error) { setCrews(current => current.map(c => c.id === crew.id ? { ...c, membership: { ...c.membership, share_summary: previous } } : c)); throw error; } }); }} /><span><strong>이 크루에 나의 훈련 요약 공유</strong><small>최근 거리와 횟수 집계에만 포함됩니다. GPS 원본·심박·개별 기록은 공유되지 않습니다.</small></span></label>{crewSummary && (crewSummary.suppressed ? <div className="notice">현재 {crewSummary.consenting_members}명이 동의했습니다. 3명 이상 동의하면 집계가 표시됩니다.</div> : <div className="metrics"><Metric label="동의한 활성 회원" value={fmt(crewSummary.consenting_members, 0)} unit="명" icon={<Users size={17} />} /><Metric label="크루 누적 거리" value={fmt(crewSummary.distance_km)} unit="km" icon={<Footprints size={17} />} /><Metric label="크루 러닝" value={fmt(crewSummary.run_count, 0)} unit="회" icon={<Activity size={17} />} /></div>)}{isManager && <div className="invite-box"><button className="button" disabled={busy} onClick={() => action(async () => { const result = await api<{ code: string }>(`/crews/${crew.id}/invites`, { method: "POST" }); setInviteCode(result.code); })}>7일 초대 코드 발급</button>{inviteCode && <label>초대 코드 (운영자가 직접 전달)<input readOnly value={inviteCode} onFocus={e => e.target.select()} /></label>}</div>}<h3 className="subheading">크루 회원</h3>{crewDetail?.members.map(m => <div className="member-row" key={m.user_id}><div><strong>{m.user_id === profile.id ? `${profile.display_name} (나)` : `러너 ${m.user_id.slice(0, 8)}`}</strong><small>{m.role} · {m.status}</small></div><div className="row">{isManager && m.status === "pending" && <>{["active", "rejected"].map(status => <button key={status} className="button small" disabled={busy} onClick={() => action(async () => { await api(`/crews/${crew.id}/members/${m.user_id}`, { method: "PATCH", body: jsonBody({ status }) }); await refreshCrew(crew.id); })}>{status === "active" ? "승인" : "거절"}</button>)}</>}{crew.membership.role === "owner" && m.status === "active" && m.role !== "owner" && <><button className="button small" disabled={busy} onClick={() => action(async () => { await api(`/crews/${crew.id}/members/${m.user_id}`, { method: "PATCH", body: jsonBody({ role: m.role === "admin" ? "member" : "admin" }) }); await refreshCrew(crew.id); })}>{m.role === "admin" ? "관리자 해제" : "관리자 지정"}</button><button className="text-button" disabled={busy} onClick={() => { if (window.confirm("이 회원에게 소유권을 양도할까요?")) action(async () => { await api(`/crews/${crew.id}/transfer`, { method: "POST", body: jsonBody({ user_id: m.user_id }) }); await refreshData(); await refreshCrew(crew.id); }); }}>소유권 양도</button></>}</div></div>)}{crew.membership.role !== "owner" && <button className="button danger" disabled={busy} onClick={() => { if (window.confirm("크루를 탈퇴할까요?")) action(async () => { await api(`/crews/${crew.id}/membership`, { method: "DELETE" }); setCrewId(""); await refreshData(); }); }}>크루 탈퇴</button>}<p className="fine">운영자에게 개인 상세 기록 접근권은 부여되지 않습니다. 회원 목록에는 개인정보 대신 식별 코드가 표시됩니다.</p></Card>}</>}

    {tab === "settings" && <><Card><AthleteForm profile={profile} onSaved={setProfile} /></Card><Card><div className="section-heading"><div><h2>프로필과 러닝 목표</h2><p>목표는 참고값입니다. 훈련은 최근 이력에 맞춥니다.</p></div><span className="pill">나만 공개</span></div><form key={profile.id + profile.display_name + profile.goal_distance_km + profile.goal_time_min + profile.runs_per_week} className="profile-form" onSubmit={e => { e.preventDefault(); const values = new FormData(e.currentTarget); action(async () => { const next = await api<Profile>("/profile", { method: "PATCH", body: jsonBody({ display_name: values.get("display_name"), goal_distance_km: values.get("goal_distance_km") ? Number(values.get("goal_distance_km")) : null, goal_time_min: values.get("goal_time_min") ? Number(values.get("goal_time_min")) : null, runs_per_week: Number(values.get("runs_per_week")) }) }); setProfile(next); message("프로필과 목표를 저장했습니다. 이미 생성한 이번 주 계획은 유지됩니다."); }); }}><label>표시 이름<input name="display_name" required maxLength={40} defaultValue={profile.display_name} /></label><label>주당 달리기 횟수<select name="runs_per_week" defaultValue={profile.runs_per_week}>{[2, 3, 4, 5].map(v => <option key={v} value={v}>{v}회</option>)}</select></label><label>목표 거리 (km)<input name="goal_distance_km" type="number" min="0.1" max="100" step="0.1" defaultValue={profile.goal_distance_km ?? ""} placeholder="예: 10" /></label><label>목표 시간 (분)<input name="goal_time_min" type="number" min="0.1" max="1440" step="0.1" defaultValue={profile.goal_time_min ?? ""} placeholder="예: 60" /></label><button className="button primary" disabled={busy}>설정 저장 <Check size={16} /></button></form></Card><Card><h2>나의 데이터</h2><p className="muted">원본 GPX·FIT, 분석, 프로필, 크루 가입 내역과 훈련 계획을 ZIP 파일로 내보냅니다.</p><div className="row button-row"><button className="button" disabled={busy} onClick={() => download("/account/export", "running-coach-export.zip")}><ArrowDownToLine size={16} /> 데이터 내보내기</button><button className="button" disabled={busy} onClick={() => action(async () => { await api("/auth/logout", { method: "POST" }); setProfile(null); setRuns([]); setPlans([]); setCrews([]); setDashboard(null); setCrewId(""); setTab("overview"); })}><LogOut size={16} /> 로그아웃</button></div></Card><Card><h2>계정 삭제</h2><p className="muted">원본 파일과 모든 개인 데이터가 영구 삭제됩니다. 소유한 크루는 먼저 양도하고, 삭제 전 15분 이내에 다시 로그인하세요.</p><form className="inline-form" onSubmit={e => { e.preventDefault(); const confirm = new FormData(e.currentTarget).get("confirm"); if (window.confirm("계정과 모든 개인 데이터를 영구 삭제할까요?")) action(async () => { await api("/account", { method: "DELETE", body: jsonBody({ confirm }) }); window.location.reload(); }); }}><input name="confirm" aria-label="삭제 확인 문구" required pattern="DELETE" placeholder="DELETE 입력" /><button className="button danger" disabled={busy}><Trash2 size={16} /> 계정 영구 삭제</button></form></Card><Card><h2>앱 설치</h2><p className="muted">{install ? "설치 버튼으로 홈 화면에 PACE를 추가하세요." : "모바일 Safari: 공유 → 홈 화면에 추가. Chrome: 브라우저 메뉴 → 앱 설치. HTTPS 또는 localhost에서 지원합니다."}</p>{install && <button className="button" onClick={() => action(async () => { await install.prompt(); await install.userChoice; setInstall(null); })}>PACE 설치</button>}<p className="fine">오프라인에서는 연결 안내만 표시합니다. 개인 기록과 API 응답을 캐시하지 않습니다.</p></Card></>}
    <footer className="footer"><span className="brand small-brand">PACE<span>↗</span></span><span>YOUR PACE. YOUR PROGRESS.</span><span><ShieldCheck size={13} /> 기본 비공개 · 나의 동의로 공유</span></footer></main></div><nav className="mobile-nav" aria-label="모바일 메뉴">{links.map(link => <button key={link.id} className={tab === link.id ? "active" : ""} onClick={() => { setTab(link.id); setSelectedId(null); }}><link.icon size={20} /><span>{link.title}</span></button>)}</nav></div>;
}
