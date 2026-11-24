CREATE TABLE emergency108_handoff (
    run_id uuid NOT NULL REFERENCES simulation_run(id),
    assignment_ref bigint NOT NULL CHECK (assignment_ref > 0),
    emergency_ref bigint NOT NULL CHECK (emergency_ref > 0),
    ambulance_ref bigint NOT NULL CHECK (ambulance_ref > 0),
    destination_ref bigint NOT NULL CHECK (destination_ref > 0),
    journey_leg text NOT NULL CHECK (journey_leg = 'TO_HOSPITAL'),
    ambulance_id text NOT NULL,
    origin text NOT NULL,
    destination text NOT NULL,
    submission_command uuid NOT NULL,
    authorization_command uuid,
    status text NOT NULL CHECK (status IN ('PENDING_AUTHORIZATION', 'AUTHORIZED', 'SUPERSEDED')),
    replaced_by bigint,
    PRIMARY KEY (run_id, assignment_ref),
    FOREIGN KEY (run_id, submission_command) REFERENCES run_command(run_id, id),
    FOREIGN KEY (run_id, authorization_command) REFERENCES run_command(run_id, id),
    FOREIGN KEY (run_id, replaced_by) REFERENCES emergency108_handoff(run_id, assignment_ref)
);

CREATE UNIQUE INDEX emergency108_current_emergency
    ON emergency108_handoff(run_id, emergency_ref, journey_leg) WHERE status <> 'SUPERSEDED';
CREATE UNIQUE INDEX emergency108_reserved_ambulance
    ON emergency108_handoff(run_id, ambulance_id) WHERE status <> 'SUPERSEDED';
