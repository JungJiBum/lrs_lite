ALTER TABLE statements
    ADD COLUMN actor_key TEXT,
    ADD COLUMN verb_id TEXT,
    ADD COLUMN activity_id TEXT,
    ADD COLUMN event_timestamp TIMESTAMPTZ,
    ADD COLUMN score_scaled DOUBLE PRECISION,
    ADD COLUMN success BOOLEAN,
    ADD COLUMN completion BOOLEAN;

UPDATE statements
SET actor_key = CASE
        WHEN jsonb_typeof(payload->'actor'->'mbox') = 'string'
         AND payload #>> '{actor,mbox}' ~ '^mailto:[^@]+@[^@]+$'
        THEN 'mbox:'
             || split_part(payload #>> '{actor,mbox}', '@', 1)
             || '@'
             || lower(split_part(payload #>> '{actor,mbox}', '@', 2))
        ELSE NULL
    END,
    verb_id = CASE
        WHEN jsonb_typeof(payload->'verb'->'id') = 'string'
        THEN payload #>> '{verb,id}'
        ELSE NULL
    END,
    activity_id = CASE
        WHEN jsonb_typeof(payload->'object'->'id') = 'string'
        THEN payload #>> '{object,id}'
        ELSE NULL
    END,
    event_timestamp = CASE
        WHEN jsonb_typeof(payload->'timestamp') = 'string'
         AND payload->>'timestamp' ~ '([zZ]|[+-][0-9]{2}:[0-9]{2})$'
         AND pg_input_is_valid(payload->>'timestamp', 'timestamp with time zone')
        THEN (payload->>'timestamp')::TIMESTAMPTZ
        ELSE received_at
    END,
    score_scaled = CASE
        WHEN jsonb_typeof(payload->'result'->'score'->'scaled') = 'number'
         AND pg_input_is_valid(
             payload #>> '{result,score,scaled}',
             'double precision'
         )
         AND (payload #>> '{result,score,scaled}')::DOUBLE PRECISION BETWEEN -1 AND 1
        THEN (payload #>> '{result,score,scaled}')::DOUBLE PRECISION
        ELSE NULL
    END,
    success = CASE
        WHEN jsonb_typeof(payload->'result'->'success') = 'boolean'
        THEN (payload #>> '{result,success}')::BOOLEAN
        ELSE NULL
    END,
    completion = CASE
        WHEN jsonb_typeof(payload->'result'->'completion') = 'boolean'
        THEN (payload #>> '{result,completion}')::BOOLEAN
        ELSE NULL
    END;

ALTER TABLE statements
    ALTER COLUMN event_timestamp SET NOT NULL,
    ADD CONSTRAINT statements_score_scaled_range
        CHECK (score_scaled IS NULL OR score_scaled BETWEEN -1 AND 1);

CREATE INDEX idx_statements_actor_key ON statements (actor_key);
