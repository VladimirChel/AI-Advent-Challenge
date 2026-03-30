BEGIN;

-- Needed for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1) messages: add branch-aware columns for MVP branching
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS message_uuid TEXT,
    ADD COLUMN IF NOT EXISTS branch_id TEXT,
    ADD COLUMN IF NOT EXISTS parent_message_uuid TEXT;

UPDATE messages
SET branch_id = 'main'
WHERE branch_id IS NULL OR btrim(branch_id) = '';

ALTER TABLE messages
    ALTER COLUMN branch_id SET DEFAULT 'main';

ALTER TABLE messages
    ALTER COLUMN branch_id SET NOT NULL;

UPDATE messages
SET message_uuid = gen_random_uuid()::text
WHERE message_uuid IS NULL OR btrim(message_uuid) = '';

ALTER TABLE messages
    ALTER COLUMN message_uuid SET NOT NULL;

-- Drop old uniqueness by (conversation_id, seq_no), because seq_no is now per branch.
DROP INDEX IF EXISTS uniq_messages_seq;
DROP INDEX IF EXISTS idx_messages_conversation_seq;

-- Recreate indexes for branch-aware reads/writes.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_message_uuid
    ON messages (message_uuid);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_branch_seq
    ON messages (conversation_id, branch_id, seq_no DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_branch_seq
    ON messages (conversation_id, branch_id, seq_no);

-- 2) conversation_summaries: switch PK from (conversation_id) to (conversation_id, branch_id)
ALTER TABLE conversation_summaries
    ADD COLUMN IF NOT EXISTS branch_id TEXT;

UPDATE conversation_summaries
SET branch_id = 'main'
WHERE branch_id IS NULL OR btrim(branch_id) = '';

ALTER TABLE conversation_summaries
    ALTER COLUMN branch_id SET DEFAULT 'main';

ALTER TABLE conversation_summaries
    ALTER COLUMN branch_id SET NOT NULL;

DO $$
DECLARE
    pk_name text;
BEGIN
    SELECT tc.constraint_name
    INTO pk_name
    FROM information_schema.table_constraints tc
    WHERE tc.table_schema = current_schema()
      AND tc.table_name = 'conversation_summaries'
      AND tc.constraint_type = 'PRIMARY KEY';

    IF pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE conversation_summaries DROP CONSTRAINT %I', pk_name);
    END IF;
END $$;

ALTER TABLE conversation_summaries
    ADD CONSTRAINT conversation_summaries_pkey
    PRIMARY KEY (conversation_id, branch_id);

-- 3) conversation_facts: switch PK from (conversation_id, key) to (conversation_id, branch_id, key)
ALTER TABLE conversation_facts
    ADD COLUMN IF NOT EXISTS branch_id TEXT;

UPDATE conversation_facts
SET branch_id = 'main'
WHERE branch_id IS NULL OR btrim(branch_id) = '';

ALTER TABLE conversation_facts
    ALTER COLUMN branch_id SET DEFAULT 'main';

ALTER TABLE conversation_facts
    ALTER COLUMN branch_id SET NOT NULL;

DO $$
DECLARE
    pk_name text;
BEGIN
    SELECT tc.constraint_name
    INTO pk_name
    FROM information_schema.table_constraints tc
    WHERE tc.table_schema = current_schema()
      AND tc.table_name = 'conversation_facts'
      AND tc.constraint_type = 'PRIMARY KEY';

    IF pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE conversation_facts DROP CONSTRAINT %I', pk_name);
    END IF;
END $$;

ALTER TABLE conversation_facts
    ADD CONSTRAINT conversation_facts_pkey
    PRIMARY KEY (conversation_id, branch_id, key);

DROP INDEX IF EXISTS idx_conversation_facts_updated;
CREATE INDEX IF NOT EXISTS idx_conversation_facts_updated
    ON conversation_facts (conversation_id, branch_id, updated_at DESC);

COMMIT;
