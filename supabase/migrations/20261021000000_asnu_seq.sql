-- App-issued request IDs: ASNUF0, ASNUF1, … (separate from Gravity ASNU#####).
-- nextval is concurrency-safe without advisory locks.

DROP SEQUENCE IF EXISTS public.asnu_seq;
DROP INDEX IF EXISTS public.mr_asnu_app_unique;

CREATE SEQUENCE public.asnu_seq
    AS bigint
    INCREMENT BY 1
    MINVALUE 0
    START WITH 0
    NO CYCLE;

-- If ASNUF* already exist, bump past the highest suffix (else leave at 0).
DO $$
DECLARE
  mx bigint;
BEGIN
  SELECT MAX(substring(asnu FROM '[0-9]+')::bigint)
    INTO mx
  FROM public.maintenance_request
  WHERE asnu ~* '^asnuf[0-9]+$';

  IF mx IS NOT NULL THEN
    PERFORM setval('public.asnu_seq', mx, true);
  END IF;
END $$;

CREATE UNIQUE INDEX mr_asnu_app_unique
    ON public.maintenance_request (asnu)
    WHERE asnu ~* '^asnuf[0-9]+$';
