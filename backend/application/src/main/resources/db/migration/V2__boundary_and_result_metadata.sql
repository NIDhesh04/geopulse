ALTER TABLE run_command ADD COLUMN boundary_ordinal bigint;
ALTER TABLE simulation_run ADD COLUMN ambulance_result jsonb;
