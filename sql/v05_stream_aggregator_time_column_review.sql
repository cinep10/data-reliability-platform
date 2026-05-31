-- v0.5 stream aggregator time column review

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema=DATABASE()
  AND table_name='stg_event_stream'
  AND column_name IN ('event_ts','ts','ingest_ts','producer_ts','created_at')
ORDER BY FIELD(column_name,'event_ts','ts','ingest_ts','producer_ts','created_at');

SELECT
  dt,
  profile_id,
  COUNT(*) AS stg_event_stream_rows,
  MIN(ts) AS min_ts,
  MAX(ts) AS max_ts,
  MIN(ingest_ts) AS min_ingest_ts,
  MAX(ingest_ts) AS max_ingest_ts
FROM stg_event_stream
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-21'
GROUP BY dt, profile_id;

SELECT *
FROM stream_reliability_summary_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-21'
ORDER BY dt DESC
LIMIT 10;
