CREATE TABLE scenario_definition (
 id text PRIMARY KEY, version integer NOT NULL, definition jsonb NOT NULL
);
CREATE TABLE simulation_run (
 id uuid PRIMARY KEY, scenario_id text NOT NULL REFERENCES scenario_definition(id),
 scenario_snapshot jsonb NOT NULL, seed bigint NOT NULL, horizon text NOT NULL,
 status text NOT NULL CHECK (status IN ('PAUSED','RUNNING','COMPLETED','INTERRUPTED')),
 revision bigint NOT NULL DEFAULT 0, acceptance_sequence bigint NOT NULL DEFAULT 0,
 event_sequence bigint NOT NULL DEFAULT 0, simulation_time bigint NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE run_command (
 run_id uuid NOT NULL REFERENCES simulation_run(id), id uuid NOT NULL,
 acceptance_sequence bigint NOT NULL, type text NOT NULL, payload jsonb NOT NULL,
 status text NOT NULL CHECK (status IN ('ACCEPTED','APPLIED','REJECTED')),
 applied_tick bigint, reason text, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(run_id,id), UNIQUE(run_id,acceptance_sequence)
);
CREATE TABLE run_event (
 run_id uuid NOT NULL REFERENCES simulation_run(id), sequence bigint NOT NULL,
 tick bigint NOT NULL, type text NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(run_id,sequence)
);
