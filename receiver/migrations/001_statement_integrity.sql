LOCK TABLE statements IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    invalid_count BIGINT;
    duplicate_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO invalid_count
    FROM statements
    WHERE statement_id IS NULL
       OR statement_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

    IF invalid_count > 0 THEN
        RAISE EXCEPTION
            'statement integrity migration blocked: % row(s) have a missing or invalid UUID',
            invalid_count;
    END IF;

    SELECT COUNT(*)
    INTO duplicate_count
    FROM (
        SELECT statement_id
        FROM statements
        GROUP BY statement_id
        HAVING COUNT(*) > 1
    ) duplicates;

    IF duplicate_count > 0 THEN
        RAISE EXCEPTION
            'statement integrity migration blocked: % duplicate statement id(s) require review',
            duplicate_count;
    END IF;
END
$$;

ALTER TABLE statements
    ALTER COLUMN statement_id TYPE UUID USING statement_id::UUID,
    ALTER COLUMN statement_id SET NOT NULL;

ALTER TABLE statements
    ADD CONSTRAINT statements_statement_id_key UNIQUE (statement_id);
