-- NORVIM DealFinder 2.0 prototype schema
-- Run in the Supabase SQL editor.
-- Service-role credentials must stay server-side in Streamlit Secrets.

create extension if not exists pgcrypto;

create table if not exists organizations (
  id text primary key,
  name text not null,
  created_at timestamptz not null default now()
);

insert into organizations (id, name)
values ('norvim', 'NORVIM 13 LLC')
on conflict (id) do nothing;

create table if not exists properties (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  normalized_address text not null,
  rentcast_id text,
  address text,
  city text,
  state text,
  zip_code text,
  property_type text,
  bedrooms numeric,
  bathrooms numeric,
  square_footage numeric,
  latitude double precision,
  longitude double precision,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, normalized_address)
);

create table if not exists analysis_snapshots (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  normalized_address text not null,
  address text,
  snapshot jsonb not null,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index if not exists analysis_snapshots_lookup_idx
  on analysis_snapshots (org_id, normalized_address, fetched_at desc);

create table if not exists underwriting_runs (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  property_id uuid not null references properties(id) on delete cascade,
  normalized_address text,
  selected_strategy text,
  purchase_price numeric,
  strategy_results jsonb,
  assumptions jsonb,
  created_at timestamptz not null default now()
);

create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  property_id uuid not null references properties(id) on delete cascade,
  status text default 'New Lead',
  lead_source text,
  seller_name text,
  seller_phone text,
  seller_email text,
  partner text,
  preferred_strategy text,
  seller_ask numeric,
  offer_amount numeric,
  follow_up_date date,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, property_id)
);

create or replace view lead_pipeline as
select
  l.org_id,
  l.property_id,
  p.address,
  p.city,
  p.state,
  p.zip_code,
  l.status,
  l.lead_source,
  l.preferred_strategy,
  l.seller_ask,
  l.offer_amount,
  l.follow_up_date,
  l.partner,
  l.notes,
  l.updated_at
from leads l
join properties p on p.id = l.property_id;

create table if not exists api_usage (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  provider text not null,
  endpoint text,
  normalized_address text,
  occurred_at timestamptz not null default now()
);
create index if not exists api_usage_month_idx
  on api_usage (org_id, provider, occurred_at desc);

-- SaaS-ready data model placeholders.
-- Full multi-user auth and billing should be wired to Supabase Auth + Stripe before public launch.
create table if not exists organization_members (
  org_id text not null references organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member',
  created_at timestamptz not null default now(),
  primary key (org_id, user_id)
);

create table if not exists subscriptions (
  id uuid primary key default gen_random_uuid(),
  org_id text not null references organizations(id) on delete cascade,
  stripe_customer_id text,
  stripe_subscription_id text,
  plan_name text,
  status text,
  current_period_end timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table properties enable row level security;
alter table analysis_snapshots enable row level security;
alter table underwriting_runs enable row level security;
alter table leads enable row level security;
alter table api_usage enable row level security;
alter table organization_members enable row level security;
alter table subscriptions enable row level security;

-- The prototype app uses the server-side service-role key and therefore bypasses RLS.
-- Before public SaaS launch, add Supabase Auth and organization-scoped RLS policies.
