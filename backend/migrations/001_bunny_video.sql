-- Apply ONCE to an EXISTING Postgres DB before deploying code with bunny_video_id.
-- On a new DB, Base.metadata.create_all creates this column automatically.
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS bunny_video_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_episodes_bunny_video_id ON episodes (bunny_video_id);
