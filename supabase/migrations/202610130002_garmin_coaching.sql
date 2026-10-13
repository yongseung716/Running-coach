-- Additive upgrade: preserves existing profiles, activities, crews and plans.
begin;
alter table public.profiles add column if not exists athlete_settings jsonb not null default '{}'::jsonb;
alter table public.runs add column if not exists workout_notes jsonb not null default '{}'::jsonb;

-- Replace only the file path constraint; retain all status and ownership checks.
do $$ declare c record; begin
 for c in select conname from pg_constraint
  where conrelid='public.runs'::regclass and contype='c' and pg_get_constraintdef(oid) like '%file_key%' loop
  execute format('alter table public.runs drop constraint %I',c.conname);
 end loop;
end $$;
alter table public.runs add constraint runs_private_file_path check(
 file_key=user_id::text||'/'||id::text||'.gpx' or file_key=user_id::text||'/'||id::text||'.fit'
);
grant update(athlete_settings) on public.profiles to authenticated;
grant update(workout_notes) on public.runs to authenticated;
drop policy if exists run_notes_write on public.runs;
create policy run_notes_write on public.runs for update to authenticated
 using(user_id=auth.uid()) with check(user_id=auth.uid());
grant update(prescription) on public.plans to authenticated;
drop policy if exists plan_edit on public.plans;
create policy plan_edit on public.plans for update to authenticated
 using(user_id=auth.uid()) with check(user_id=auth.uid());

create or replace function public.request_reanalysis(p_run uuid) returns boolean
 language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.runs where id=p_run and user_id=auth.uid()) then raise exception 'Activity unavailable'; end if;
 update public.runs set status='queued',attempts=0,analysis=null,error=null,lease_until=null
  where id=p_run and user_id=auth.uid() and status in ('completed','failed');
 return found;
end $$;
revoke execute on function public.request_reanalysis(uuid) from public,anon;
grant execute on function public.request_reanalysis(uuid) to authenticated;
create or replace function public.protect_completed_plan_days() returns trigger
 language plpgsql security definer set search_path='' as $$
declare item record;
begin
 for item in select day_index from public.completions where plan_id=old.id loop
  if old.prescription->'days'->item.day_index is distinct from new.prescription->'days'->item.day_index then
   raise exception 'Uncomplete the day before editing';
  end if;
 end loop;
 return new;
end $$;
revoke execute on function public.protect_completed_plan_days() from public,anon,authenticated;
drop trigger if exists protect_completed_days on public.plans;
create trigger protect_completed_days before update of prescription on public.plans
 for each row execute function public.protect_completed_plan_days();
update storage.buckets set allowed_mime_types=array['application/gpx+xml','application/octet-stream'] where id='gpx-private';
commit;
