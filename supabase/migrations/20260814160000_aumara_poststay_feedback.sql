create extension if not exists pgcrypto;

create table if not exists public.aumara_feedback_codes (
  discount_code text primary key,
  survey_token_hash text not null unique,
  property_id bigint not null default 324882,
  booking_ref bigint not null unique,
  channel_confirmation text,
  guest_first_name text not null,
  guest_display_name text not null,
  guest_language text not null default 'en'
    check (guest_language in ('en', 'es', 'it', 'ru')),
  room_type text,
  stay_arrival date not null,
  stay_departure date not null,
  discount_percent numeric(5,2) not null default 10.00
    check (discount_percent > 0 and discount_percent <= 100),
  min_nights smallint not null default 5
    check (min_nights >= 1),
  transferable boolean not null default true,
  stackable boolean not null default true,
  max_redemptions smallint not null default 1
    check (max_redemptions >= 1),
  redemptions_used smallint not null default 0
    check (redemptions_used >= 0),
  active boolean not null default true,
  beds24_status text not null default 'requires_activation'
    check (beds24_status in ('requires_activation', 'active', 'disabled', 'redeemed')),
  survey_submitted_at timestamptz,
  issued_at timestamptz not null default now(),
  expires_at date,
  redeemed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (stay_departure > stay_arrival),
  check (redemptions_used <= max_redemptions),
  check (discount_code ~ '^[A-Z0-9]{8,32}$'),
  check (survey_token_hash ~ '^[a-f0-9]{64}$')
);

create table if not exists public.aumara_guest_feedback (
  id uuid primary key default gen_random_uuid(),
  discount_code text not null unique
    references public.aumara_feedback_codes(discount_code)
    on update cascade on delete restrict,
  overall_rating smallint not null
    check (overall_rating between 1 and 5),
  recommend_score smallint not null
    check (recommend_score between 0 and 10),
  liked text[] not null default '{}',
  improvement_text text not null default '',
  add_wishlist text[] not null default '{}',
  activity_interests text[] not null default '{}',
  final_comment text not null default '',
  testimonial_consent boolean not null default false,
  locale text not null default 'en'
    check (locale in ('en', 'es', 'it', 'ru')),
  submitted_at timestamptz not null default now(),
  check (cardinality(liked) <= 8),
  check (cardinality(add_wishlist) <= 8),
  check (cardinality(activity_interests) <= 10),
  check (char_length(improvement_text) <= 1200),
  check (char_length(final_comment) <= 1200)
);

create table if not exists public.aumara_feedback_events (
  id bigint generated always as identity primary key,
  discount_code text not null
    references public.aumara_feedback_codes(discount_code)
    on update cascade on delete restrict,
  event_type text not null
    check (event_type in (
      'issued',
      'survey_opened',
      'survey_submitted',
      'booking_link_opened',
      'redeemed',
      'disabled'
    )),
  metadata jsonb not null default '{}'::jsonb,
  event_at timestamptz not null default now()
);

create index if not exists aumara_feedback_events_code_time_idx
  on public.aumara_feedback_events(discount_code, event_at desc);

alter table public.aumara_feedback_codes enable row level security;
alter table public.aumara_guest_feedback enable row level security;
alter table public.aumara_feedback_events enable row level security;

revoke all on public.aumara_feedback_codes from public, anon, authenticated;
revoke all on public.aumara_guest_feedback from public, anon, authenticated;
revoke all on public.aumara_feedback_events from public, anon, authenticated;
revoke all on sequence public.aumara_feedback_events_id_seq from public, anon, authenticated;

grant select, insert, update, delete on public.aumara_feedback_codes to service_role;
grant select, insert, update, delete on public.aumara_guest_feedback to service_role;
grant select, insert, update, delete on public.aumara_feedback_events to service_role;
grant usage, select on sequence public.aumara_feedback_events_id_seq to service_role;

create or replace function public.aumara_submit_feedback(
  p_token_hash text,
  p_overall_rating smallint,
  p_recommend_score smallint,
  p_liked text[],
  p_improvement_text text,
  p_add_wishlist text[],
  p_activity_interests text[],
  p_final_comment text,
  p_testimonial_consent boolean,
  p_locale text
)
returns table(
  discount_code text,
  discount_percent numeric,
  min_nights smallint,
  transferable boolean,
  stackable boolean,
  expires_at date,
  beds24_status text
)
language plpgsql
set search_path to 'public'
as $function$
declare
  v_code public.aumara_feedback_codes%rowtype;
begin
  select *
    into v_code
    from public.aumara_feedback_codes
   where survey_token_hash = p_token_hash
     and active = true
   for update;

  if not found then
    raise exception using errcode = 'P0002', message = 'invalid_or_inactive_token';
  end if;

  if v_code.expires_at is not null and current_date > v_code.expires_at then
    raise exception using errcode = 'P0002', message = 'expired_token';
  end if;

  if v_code.survey_submitted_at is null then
    insert into public.aumara_guest_feedback (
      discount_code,
      overall_rating,
      recommend_score,
      liked,
      improvement_text,
      add_wishlist,
      activity_interests,
      final_comment,
      testimonial_consent,
      locale
    ) values (
      v_code.discount_code,
      p_overall_rating,
      p_recommend_score,
      coalesce(p_liked, '{}'::text[]),
      coalesce(p_improvement_text, ''),
      coalesce(p_add_wishlist, '{}'::text[]),
      coalesce(p_activity_interests, '{}'::text[]),
      coalesce(p_final_comment, ''),
      coalesce(p_testimonial_consent, false),
      p_locale
    );

    update public.aumara_feedback_codes
       set survey_submitted_at = now(),
           updated_at = now()
     where public.aumara_feedback_codes.discount_code = v_code.discount_code;

    insert into public.aumara_feedback_events (
      discount_code,
      event_type,
      metadata
    ) values (
      v_code.discount_code,
      'survey_submitted',
      jsonb_build_object('locale', p_locale)
    );
  end if;

  return query
  select c.discount_code,
         c.discount_percent,
         c.min_nights,
         c.transferable,
         c.stackable,
         c.expires_at,
         c.beds24_status
    from public.aumara_feedback_codes c
   where c.discount_code = v_code.discount_code;
end;
$function$;

revoke execute on function public.aumara_submit_feedback(
  text, smallint, smallint, text[], text, text[], text[], text, boolean, text
) from public, anon, authenticated;

grant execute on function public.aumara_submit_feedback(
  text, smallint, smallint, text[], text, text[], text[], text, boolean, text
) to service_role;

comment on table public.aumara_feedback_codes is
  'AUMARA post-stay survey bearer-token hashes and transferable discount codes.';
comment on table public.aumara_guest_feedback is
  'One post-stay feedback submission per issued AUMARA discount code.';
comment on table public.aumara_feedback_events is
  'Minimal audit trail for the AUMARA survey and booking-link lifecycle.';
