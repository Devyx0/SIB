-- Add receptionist staff role (intake-only; permissions enforced in app).
ALTER TABLE public.employee_role
    DROP CONSTRAINT IF EXISTS employee_role_role_check;

ALTER TABLE public.employee_role
    ADD CONSTRAINT employee_role_role_check CHECK (
        (role)::text = ANY (
            (ARRAY[
                'admin'::character varying,
                'director'::character varying,
                'coordinator'::character varying,
                'technician'::character varying,
                'contractor'::character varying,
                'receptionist'::character varying
            ])::text[]
        )
    );
