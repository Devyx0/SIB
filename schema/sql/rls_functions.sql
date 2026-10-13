-- rls_functions.sql — SECURITY DEFINER helpers for RLS policies.
--
-- Apply via Supabase SQL editor or psql (as superuser/postgres role).
-- These must exist before rls_policies.sql is applied.
--
-- All functions use SET search_path = public, auth so that:
--   - auth.uid() resolves correctly
--   - No search_path injection is possible

-- Resolves current auth.uid() → employee_id.
-- Returns NULL if no employee row matches (unauthenticated or no login yet).
CREATE OR REPLACE FUNCTION current_employee_id()
RETURNS integer LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, auth
AS $$
  SELECT employee_id FROM employee WHERE auth_user_id = auth.uid() LIMIT 1;
$$;

-- Returns true if the current user holds the given role in employee_role.
-- Used in every USING clause — cached per statement by STABLE.
CREATE OR REPLACE FUNCTION has_role(role_name text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, auth
AS $$
  SELECT EXISTS (
    SELECT 1 FROM employee_role
    WHERE employee_id = current_employee_id()
      AND role = role_name
  );
$$;

-- Returns the set of building_ids visible to the current technician:
--   1. All buildings in the technician's own sector_id
--   2. All buildings from employee_building_assignment (A5 dedications)
-- Used in maintenance_request and followup row-scoping policies.
CREATE OR REPLACE FUNCTION technician_building_ids()
RETURNS TABLE(building_id integer) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, auth
AS $$
  SELECT b.building_id
  FROM building b
  JOIN employee e ON b.sector_id = e.sector_id
  WHERE e.employee_id = current_employee_id()
  UNION
  SELECT eba.building_id
  FROM employee_building_assignment eba
  WHERE eba.employee_id = current_employee_id()
$$;
