-- Apply via Supabase CLI migrations. Raw storage is service-only, never public.
create table public.profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 display_name text not null check(length(display_name) between 1 and 40),
 goal_distance_km double precision check(goal_distance_km > 0 and goal_distance_km <= 100),
 goal_time_min double precision check(goal_time_min > 0 and goal_time_min <= 1440),
 runs_per_week integer not null default 3 check(runs_per_week between 2 and 5),
 check((goal_distance_km is null) = (goal_time_min is null))
);
create table public.crews (
 id uuid primary key default gen_random_uuid(), name text not null check(length(name) between 1 and 60),
 owner_id uuid not null references public.profiles(id)
);
create table public.memberships (
 crew_id uuid references public.crews(id) on delete cascade,
 user_id uuid references public.profiles(id) on delete cascade,
 role text not null default 'member' check(role in ('owner','admin','member')),
 status text not null default 'pending' check(status in ('pending','active','rejected')),
 share_summary boolean not null default false,
 primary key(crew_id,user_id), check(role <> 'owner' or status='active')
);
create unique index one_owner_per_crew on public.memberships(crew_id) where role='owner';
create index memberships_by_user on public.memberships(user_id);
create table public.invites (
 id uuid primary key default gen_random_uuid(), crew_id uuid not null references public.crews(id) on delete cascade,
 code_hash text unique not null, expires_at double precision not null
);
create table public.runs (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
 file_key text not null, sha256 text not null, created_at text not null,
 status text not null default 'queued' check(status in ('queued','processing','completed','failed')),
 error text, analysis jsonb, attempts integer not null default 0, lease_until double precision,
 unique(user_id,sha256), check(file_key = user_id::text || '/' || id::text || '.gpx')
);
create index runs_by_user on public.runs(user_id,created_at desc,id desc);
create index pending_jobs on public.runs(status,lease_until) where status in ('queued','processing');
create table public.plans (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
 week_start text not null, prescription jsonb not null, unique(user_id,week_start)
);
create table public.completions (
 plan_id uuid references public.plans(id) on delete cascade, day_index integer check(day_index between 0 and 6),
 user_id uuid not null references public.profiles(id) on delete cascade,
 run_id uuid references public.runs(id) on delete set null, completed_at text not null,
 primary key(plan_id,day_index)
);

create function public.on_new_user() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.profiles(id,display_name) values(new.id, left(coalesce(nullif(trim(new.raw_user_meta_data->>'display_name'),''),'Runner'),40));
 return new;
end $$;
create trigger auth_profile after insert on auth.users for each row execute function public.on_new_user();

-- Helpers avoid recursive RLS on membership reads. No arbitrary user parameter.
create function public.is_member(p_crew uuid) returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.memberships where crew_id=p_crew and user_id=auth.uid() and status='active')
$$;
create function public.is_manager(p_crew uuid) returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.memberships where crew_id=p_crew and user_id=auth.uid() and status='active' and role in ('owner','admin'))
$$;
create function public.has_membership(p_crew uuid) returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.memberships where crew_id=p_crew and user_id=auth.uid())
$$;

alter table public.profiles enable row level security;
alter table public.crews enable row level security;
alter table public.memberships enable row level security;
alter table public.invites enable row level security;
alter table public.runs enable row level security;
alter table public.plans enable row level security;
alter table public.completions enable row level security;

create policy profile_read on public.profiles for select to authenticated using(id=auth.uid());
create policy profile_write on public.profiles for update to authenticated using(id=auth.uid()) with check(id=auth.uid());
create policy crew_read on public.crews for select to authenticated using(public.has_membership(id));
create policy membership_read on public.memberships for select to authenticated using(
 user_id=auth.uid() or public.is_manager(crew_id) or (status='active' and public.is_member(crew_id))
);
create policy membership_leave on public.memberships for delete to authenticated using(user_id=auth.uid() and role<>'owner');
create policy invite_read on public.invites for select to authenticated using(public.is_manager(crew_id));
create policy invite_create on public.invites for insert to authenticated with check(public.is_manager(crew_id));
create policy run_read on public.runs for select to authenticated using(user_id=auth.uid());
create policy run_create on public.runs for insert to authenticated with check(
 user_id=auth.uid() and status='queued' and analysis is null and attempts=0 and error is null and lease_until is null
);
create policy run_delete on public.runs for delete to authenticated using(user_id=auth.uid());
create policy plan_read on public.plans for select to authenticated using(user_id=auth.uid());
create policy plan_create on public.plans for insert to authenticated with check(user_id=auth.uid());
create policy completion_read on public.completions for select to authenticated using(user_id=auth.uid());
create policy completion_create on public.completions for insert to authenticated with check(
 user_id=auth.uid() and exists(select 1 from public.plans where id=plan_id and user_id=auth.uid())
 and (run_id is null or exists(select 1 from public.runs where id=run_id and user_id=auth.uid() and status='completed'))
);
create policy completion_write on public.completions for update to authenticated using(user_id=auth.uid()) with check(
 user_id=auth.uid() and exists(select 1 from public.plans where id=plan_id and user_id=auth.uid())
 and (run_id is null or exists(select 1 from public.runs where id=run_id and user_id=auth.uid() and status='completed'))
);
create policy completion_delete on public.completions for delete to authenticated using(user_id=auth.uid());

-- Table ACLs also restrict attacks that would otherwise alter role, status or analysis.
revoke all on public.profiles,public.crews,public.memberships,public.invites,public.runs,public.plans,public.completions from anon,authenticated;
grant select on public.profiles,public.crews,public.memberships,public.invites,public.runs,public.plans,public.completions to authenticated;
grant update(display_name,goal_distance_km,goal_time_min,runs_per_week) on public.profiles to authenticated;
grant insert on public.invites,public.runs,public.plans,public.completions to authenticated;
grant update(run_id) on public.completions to authenticated;
grant delete on public.runs,public.memberships,public.completions to authenticated;
grant all on public.profiles,public.crews,public.memberships,public.invites,public.runs,public.plans,public.completions to service_role;

create function public.create_crew(p_name text) returns uuid language plpgsql security definer set search_path='' as $$
declare result uuid;
begin
 if auth.uid() is null then raise exception 'Authentication required'; end if;
 insert into public.crews(name,owner_id) values(p_name,auth.uid()) returning id into result;
 insert into public.memberships(crew_id,user_id,role,status) values(result,auth.uid(),'owner','active');
 return result;
end $$;
create function public.request_join(p_hash text) returns uuid language plpgsql security definer set search_path='' as $$
declare target uuid;
begin
 if auth.uid() is null then raise exception 'Authentication required'; end if;
 select crew_id into target from public.invites where code_hash=p_hash and expires_at>extract(epoch from now());
 if target is null then return null; end if;
 insert into public.memberships(crew_id,user_id) values(target,auth.uid());
 return target;
end $$;
create function public.manage_member(p_crew uuid,p_user uuid,p_status text,p_role text) returns void language plpgsql security definer set search_path='' as $$
declare caller text; target public.memberships;
begin
 perform 1 from public.crews where id=p_crew for update;
 select role into caller from public.memberships where crew_id=p_crew and user_id=auth.uid() and status='active';
 select * into target from public.memberships where crew_id=p_crew and user_id=p_user;
 if caller is null or caller not in ('owner','admin') or target.user_id is null or target.role='owner' then raise exception 'Forbidden'; end if;
 if caller='admin' and (target.role<>'member' or p_role is not null) then raise exception 'Forbidden'; end if;
 if p_status is not null and (target.status<>'pending' or p_status not in ('active','rejected')) then raise exception 'Invalid approval'; end if;
 if p_role is not null and (target.status<>'active' or p_role not in ('admin','member')) then raise exception 'Invalid role'; end if;
 update public.memberships set status=coalesce(p_status,status),role=coalesce(p_role,role) where crew_id=p_crew and user_id=p_user;
end $$;
create function public.set_consent(p_crew uuid,p_share boolean) returns void language plpgsql security definer set search_path='' as $$
begin
 if not public.is_member(p_crew) then raise exception 'Forbidden'; end if;
 update public.memberships set share_summary=p_share where crew_id=p_crew and user_id=auth.uid();
end $$;
create function public.transfer_crew(p_crew uuid,p_user uuid) returns void language plpgsql security definer set search_path='' as $$
begin
 perform 1 from public.crews where id=p_crew for update;
 if not exists(select 1 from public.crews where id=p_crew and owner_id=auth.uid())
    or p_user=auth.uid() or not exists(select 1 from public.memberships where crew_id=p_crew and user_id=p_user and status='active') then
  raise exception 'Forbidden';
 end if;
 update public.memberships set role='admin' where crew_id=p_crew and user_id=auth.uid();
 update public.memberships set role='owner' where crew_id=p_crew and user_id=p_user;
 update public.crews set owner_id=p_user where id=p_crew;
end $$;
create function public.crew_summary(p_crew uuid) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare people integer; km numeric; count_runs integer;
begin
 if not public.is_member(p_crew) then raise exception 'Forbidden'; end if;
 select count(*) into people from public.memberships where crew_id=p_crew and status='active' and share_summary;
 if people<3 then return jsonb_build_object('consenting_members',people,'suppressed',true,'distance_km',null,'run_count',null); end if;
 select coalesce(sum((r.analysis->>'distance_km')::numeric),0),count(*) into km,count_runs
 from public.runs r join public.memberships m on m.user_id=r.user_id
 where m.crew_id=p_crew and m.status='active' and m.share_summary and r.status='completed'
 and r.analysis->>'started_at' is not null
 and (r.analysis->>'started_at')::timestamptz >= ((now() at time zone 'UTC')::date - 27)::timestamp at time zone 'UTC'
 and (r.analysis->>'started_at')::timestamptz < ((now() at time zone 'UTC')::date + 1)::timestamp at time zone 'UTC';
 return jsonb_build_object('consenting_members',people,'suppressed',false,'distance_km',round(km,2),'run_count',count_runs);
end $$;

revoke execute on function public.on_new_user() from public,anon,authenticated;
revoke execute on function public.is_member(uuid), public.is_manager(uuid), public.has_membership(uuid),
 public.create_crew(text),public.request_join(text),public.manage_member(uuid,uuid,text,text),
 public.set_consent(uuid,boolean),public.transfer_crew(uuid,uuid),public.crew_summary(uuid) from public,anon;
grant execute on function public.is_member(uuid), public.is_manager(uuid), public.has_membership(uuid),
 public.create_crew(text),public.request_join(text),public.manage_member(uuid,uuid,text,text),
 public.set_consent(uuid,boolean),public.transfer_crew(uuid,uuid),public.crew_summary(uuid) to authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
 values('gpx-private','gpx-private',false,10485760,array['application/gpx+xml']);
-- No storage.objects policies: only backend service role can access original files.
