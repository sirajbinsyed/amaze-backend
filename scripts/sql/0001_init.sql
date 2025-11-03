create extension if not exists "uuid-ossp";

-- Users
create table if not exists users (
  id bigserial primary key,
  email text not null unique,
  password_hash text not null,
  role text not null check (role in (
    'admin','sales','project_manager','designer','printing','logistics','accounts','hr'
  )),
  full_name text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- CRM Leads
create table if not exists leads (
  id bigserial primary key,
  customer_name text not null,
  contact text,
  details text,
  measurements jsonb,
  photos jsonb,
  delivery_date date,
  status text not null default 'lead' check (status in ('lead','confirmed')),
  created_by bigint not null references users(id) on delete restrict,
  created_at timestamptz not null default now()
);

-- Orders
create table if not exists orders (
  id bigserial primary key,
  lead_id bigint not null unique references leads(id) on delete cascade,
  confirmed_at timestamptz default now()
);

-- Projects
create table if not exists projects (
  id bigserial primary key,
  order_id bigint not null references orders(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending','active','completed','cancelled')),
  manager_id bigint references users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- Tasks
create table if not exists tasks (
  id bigserial primary key,
  project_id bigint not null references projects(id) on delete cascade,
  type text not null check (type in ('design','printing','logistics')),
  assignee_id bigint references users(id) on delete set null,
  status text not null default 'pending' check (status in ('pending','in_progress','completed')),
  payload jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_tasks_assignee on tasks(assignee_id);
create index if not exists idx_tasks_project on tasks(project_id);
