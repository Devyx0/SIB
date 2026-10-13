-- ============================================================
-- SIB Maintenance & Operations Platform — Postgres DDL
-- Generated from schema/dbml/2_complete_system_updated.dbml
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- ENUMS
-- ════════════════════════════════════════════════════════════

CREATE TYPE urgency_tier AS ENUM (
    'AJD',  -- uppercase form present in source data
    'ajd',  -- lowercase form: both values exist, data-quality artefact from source
    'none'
);
COMMENT ON TYPE urgency_tier IS
    'AJD = aujourd''hui = urgent, handle today (guide rule 28). Both ''AJD'' and ''ajd'' exist as a data-quality artefact from source ingestion; triage service normalises to uppercase. ''none'' is a legacy ingestion artefact; the output contract uses NULL for non-urgent calls, not the string ''none''';

CREATE TYPE complexity_tier AS ENUM ('C1', 'C2', 'C3', 'C4');
COMMENT ON TYPE complexity_tier IS
    'Guide §7a (introduced 2026-07-09). C1=N''importe qui — no tool or skill required, natural pool for delegation to tenant; C2=Ouvrier — standard toolbox, limited training sufficient (label changed from "de base" on 2026-07-12, former label judged pejorative); C3=Ouvrier expérimenté/spécialité — diagnosis required, building system knowledge, real experience needed; C4=Sous-traitant/expertise externe — Newtech, Fortin, roofing, elevator, enamelling, extermination, anything requiring a quote';

CREATE TYPE congestion_level AS ENUM ('N1', 'N2', 'N3', 'N4', 'N5');
COMMENT ON TYPE congestion_level IS
    'Guide §7b (introduced 2026-07-09). N1=Au-dessus de nos affaires — fast response, minimal delegation; N2=Niveau courant — normal pace; N3=En retard — negotiate deferred scheduling for non-urgent calls, actively offer delegation; N4=Très en retard — maximum deferral, paid delegation accepted readily; N5=Critique — everything that can wait waits, delegation and subcontracting without hesitation';

CREATE TYPE report_status AS ENUM (
    'CANNOT_WAIT',
    'SUPERVISOR_DISCRETION',
    'CAN_WAIT_SHORT_TERM',
    'CAN_WAIT',
    'NOT_APPLICABLE'
);
COMMENT ON TYPE report_status IS
    'Triage reporting-obligation scale (guide §9 RAPPORT SUPERVISEUR line). CANNOT_WAIT=inform supervisor immediately; SUPERVISOR_DISCRETION=inform supervisor, timing at their discretion; CAN_WAIT_SHORT_TERM=flag for next supervisor touchpoint; CAN_WAIT=no near-term supervisor action required; NOT_APPLICABLE=report obligation does not apply to this call type';

CREATE TYPE delegable_status AS ENUM ('YES', 'NO', 'CONDITIONAL');

CREATE TYPE time_estimate_bucket AS ENUM (
    'UNDER_30_MIN',
    'MIN30_TO_1H',
    'H1_TO_2H',
    'H2_TO_4H',
    'HALF_DAY_PLUS',
    'TBD_ON_SITE'
);
COMMENT ON TYPE time_estimate_bucket IS
    'Guide §9 TEMPS line. UNDER_30_MIN=<30 min; MIN30_TO_1H=30 min–1h; H1_TO_2H=1h–2h; H2_TO_4H has no direct guide equivalent (guide jumps from 1h–2h to demi-journée, retained as intermediate bucket); HALF_DAY_PLUS=demi-journée ou journée+; TBD_ON_SITE=soumission requise (quote required before estimating — guide label and enum name diverge)';


CREATE TYPE vendor_scope AS ENUM ('portfolio_wide', 'building_specific');

CREATE TYPE shift_type AS ENUM (
    'ouverture',
    'fermeture',
    'terrain',
    'off',
    'vacances',
    'garde_urgence'
);

CREATE TYPE move_reason AS ENUM ('lease_end', 'lease_assignment', 'eviction');

-- Defined in DBML; not currently used by any column.
-- Retained for schema fidelity — may apply to future key-handoff workflow.
CREATE TYPE key_method AS ENUM ('remise_directe', 'boite_a_cle', 'bureau');

CREATE TYPE intercom_status AS ENUM ('to_do', 'done', 'call_placed');

CREATE TYPE move_type AS ENUM ('depart', 'arrivee');

CREATE TYPE time_slot AS ENUM (
    'slot_8_11',
    'slot_11_14',
    'slot_14_17',
    'slot_17_20'
);

CREATE TYPE loan_status AS ENUM ('RETIRE', 'ACHAT');

CREATE TYPE task_item_type AS ENUM (
    'jeter',
    'menage',
    'peinture',
    'plancher',
    'comptoir',
    'armoires',
    'ajout_electros'
);

CREATE TYPE payment_type AS ENUM ('coin', 'card', 'both');

CREATE TYPE pay_rule_type AS ENUM ('overage', 'percentage', 'rental');

CREATE TYPE camera_platform AS ENUM (
    'hik_connect',
    'cloud_generic',
    'ubox',
    'blink'
);

CREATE TYPE access_status_enum AS ENUM (
    'Oui_Paradox',
    'Oui_Akuvox',
    'Oui',
    'Non',
    'Installation_prevue'
);

CREATE TYPE tenancy_capacity AS ENUM (
    'named_on_lease',
    'added_occupant',
    'took_over'
);

CREATE TYPE entrance_access_method AS ENUM (
    'key',
    'fob',
    'keypad',
    'intercom_release'
);

CREATE TYPE equipment_type AS ENUM (
    'furnace',
    'boiler',
    'heat_pump',
    'elevator',
    'freight_elevator',
    'pool',
    'barbecue',
    'terrace',
    'heating',  -- heating circuit; used when splitting one Boilers source row into 2 equipment rows
    'dhw',      -- domestic hot water circuit ("ECD" = Eau Chaude Domestique); paired with heating
    'other'
);

CREATE TYPE service_contract_category AS ENUM (
    'snow',
    'lawn',
    'pool',
    'pest',
    'fire',
    'elevator',
    'telecom',
    'waste',         -- Container Rental; does not fit any of the original 7 categories
    'snow_parking',  -- Stationnement déneigement (parking lot snow removal)
    'snow_pedestrian' -- Piétonnier déneigement (pedestrian path snow removal)
);

-- NEW — cleaning_task_checklist.format_type. Source: Ménage source files showed
-- four distinct formats: structured rows, day-rotation schedules, single-line
-- descriptions, and unstructured freetext blocks.
CREATE TYPE checklist_format_type AS ENUM (
    'structured',    -- element/frequency_per_week/hours_per_visit/total all populated
    'day_rotation',  -- Day 1 / Day 2 rotation pattern
    'single_line',   -- one-line description; structured columns not applicable
    'freetext'       -- multi-line unstructured block; use raw_content column
);

CREATE TYPE service_visit_type AS ENUM (
    'fire_inspection',
    'elevator_service',
    'boiler_shutdown',
    'boiler_restart',
    'other'
);


CREATE TYPE employment_type AS ENUM ('staff', 'contractor_company', 'unknown');

CREATE TYPE source_confidence AS ENUM ('documented', 'inferred_from_calendar');

-- NEW (2026-10-09) — Triage schema additions (SoW Milestone 1, Step 1)
CREATE TYPE request_status AS ENUM (
    'intake_received',
    'triage_pending',
    'triage_clarify',
    'triage_proposal',
    'triage_failed',
    'en_route',
    'closed'
);
COMMENT ON TYPE request_status IS
$$Request lifecycle states. Auto-retry eligibility: only triage_pending and triage_failed are picked up by the retry loop. triage_clarify must NOT enter the loop — it signals a human-input requirement, not a transient error.

intake_received   — request landed (Gravity form, robot call, or in-app intake); waiting for the next triage run.
triage_pending    — acquired by the triage service; triage_started_at is set. Other workers skip. Rows stuck > 10 min = abandoned lock, eligible for takeover.
triage_clarify    — BLOCKED: triage could not proceed (ambiguous unit, address unresolvable). Requires coordinator action before the row may re-enter the queue. NEVER auto-retry: the same ambiguity will recur.
triage_proposal   — model output written and passed validation; coordinator review pending before the row appears on the dispatch board. Coordinator either accepts (→ triaged) or rejects and edits (→ triage_pending for one retry).
triage_failed     — all retries exhausted due to API error or repeated gate rejection. Auto-retry is permitted after coordinator review or manual reset.
triaged           — coordinator accepted the proposal; row is on the dispatch board. assigned_employee_id/code may or may not be set (unassigned = triaged + no employee; assigned = triaged + employee set). No separate status for those sub-states.
en_route          — field worker confirmed and heading to site. Triggers tenant SMS.
closed            — work complete and closed out. All rows ingested before 2026-10-09 carry this value as a backfill sentinel — it does not mean work was verified complete.$$;

-- ════════════════════════════════════════════════════════════
-- TABLES — dependency order (parents before children)
-- ════════════════════════════════════════════════════════════

-- ── Level 0: no FK dependencies ──────────────────────────────────────────────

CREATE TABLE project (
    project_id                  integer PRIMARY KEY,
    nom_unique_projet            varchar,
    adresse_quickbooks           varchar,
    -- NEW (2026-10-06) — Table Fondamentale Phase 1
    accounting_project_number    varchar,
    -- NEW (2026-10-07) — Table Fondamentale finance cluster (grain: project-level, confirmed)
    purchase_price               numeric,   -- TF col 14 "Prix d'achat"; NULL for Marais (no data), Chamonix (N/A)
    acquisition_date             date,      -- TF col 15 "Date d'acquisition"; NULL for Marais only
    quickbooks_class             varchar    -- TF col 5  "Nom de Classe pour Quickbooks"; NULL for Chamonix+Marais
);

CREATE TABLE sector (
    sector_id   integer PRIMARY KEY,
    territoire  varchar,  -- broader region (e.g. "QUÉBEC-EST")
    color_code  varchar
);

CREATE TABLE vendor_contact (
    vendor_id   integer PRIMARY KEY,
    trade       varchar,
    nom         varchar,
    telephone   varchar,
    notes       text
);

CREATE TABLE tenant (
    tenant_id                integer PRIMARY KEY,
    nom_complet              varchar,
    telephone                varchar,
    courriel                 varchar,
    telephone_international  varchar,
    ville                    varchar,
    code_postal              varchar,
    informations_pour_make   text
);


-- ── Level 1 ───────────────────────────────────────────────────────────────────

CREATE TABLE building (
    building_id              integer PRIMARY KEY,
    project_id               integer NOT NULL REFERENCES project(project_id),
    sector_id                integer NOT NULL REFERENCES sector(sector_id),
    adresse                  varchar,
    ville                    varchar,
    code_postal              varchar,
    annee_construction       varchar,
    nb_etages                varchar,
    nb_logements             varchar,
    ascenseur                boolean,
    piscine                  boolean,
    sauna                    boolean,
    gym                      boolean,
    chauffage                varchar,
    systeme_incendie         varchar,
    boite_a_cle_ext          varchar,  -- kept for compat; detail lives on building_key_box eventually
    boite_a_cle_int          varchar,
    raw_fiche_technique      jsonb,    -- json → jsonb for queryability
    legacy_code              varchar,  -- A002-A112 cross-ref from Fire Protection RÉF. tab. NOT unique: 31 A-codes map to 2+ buildings (A-codes are project-level, our table is building-level)
    -- NEW (2026-09-26) — Table Fondamentale + Fiches Techniques attributes (ingest_building.py Phase 1)
    sib_territory            varchar,
    furnished                varchar,
    building_structure       varchar,
    nb_elevateurs            integer,
    num_service_elevators    integer,
    internet                 varchar,
    terrasse_commune         boolean,
    num_bbqs                 integer,
    coworking_space          boolean,
    reception_loft           boolean,
    chauffage_details        text,
    chauffe_eau              varchar,
    individual_heat_pumps    boolean,
    heat_pump_details        text,
    -- NEW (2026-10-06) — Table Fondamentale Phase 1 (live sheet columns 7–14, 53–54)
    nb_units_total           integer,
    nb_units_residential     integer,
    actif_inactif            varchar,   -- "Actif" or "Inactif"
    municipality             varchar,
    property_type            varchar,
    dogs_allowed             boolean,
    web_building_name        varchar,
    web_slug                 varchar
);

CREATE TABLE employee (
    employee_id        integer PRIMARY KEY,
    initials           varchar UNIQUE,
    nom_employe        varchar,
    telephone          varchar,
    courriel           varchar,
    temps_hebdo_ete    numeric,
    temps_hebdo_hiver  numeric,
    outils_fournis     boolean,
    disponibilites     text,
    sector_id          integer REFERENCES sector(sector_id),  -- nullable; multi-sector employees use notes
    role               varchar,
    employment_type    employment_type NOT NULL DEFAULT 'unknown',
    is_active          boolean NOT NULL DEFAULT true,
    auth_user_id       uuid,                                 -- FK to auth.users once login exists
    source_confidence  source_confidence,
    notes              text
);

CREATE TABLE vendor_category_exclusivity (
    exclusivity_id  integer PRIMARY KEY,
    vendor_id       integer NOT NULL REFERENCES vendor_contact(vendor_id),
    category_label  varchar,
    scope           vendor_scope,
    rule_code       varchar
);

CREATE TABLE service_contract (
    contract_id  integer PRIMARY KEY,
    vendor_id    integer REFERENCES vendor_contact(vendor_id),
    category     service_contract_category,
    term_start   date,
    term_end     date,
    cost         numeric,
    renews       boolean,
    notes        text
);


-- ── Level 2 ───────────────────────────────────────────────────────────────────

CREATE TABLE entrance (
    entrance_id   integer PRIMARY KEY,
    building_id   integer NOT NULL REFERENCES building(building_id),
    civic_number  varchar,
    street        varchar,
    postal_code   varchar,
    access_method entrance_access_method,
    notes         text
);

CREATE TABLE unit (
    unit_id             integer PRIMARY KEY,
    building_id         integer NOT NULL REFERENCES building(building_id),
    rue                 varchar,
    numero_appartement  varchar,
    grandeur            varchar
);

CREATE TABLE building_document (
    document_id   integer PRIMARY KEY,
    building_id   integer NOT NULL REFERENCES building(building_id),
    category      varchar,
    drive_file_id varchar,
    title         varchar,
    url           varchar
);

-- Composite PK: one vendor may appear at multiple buildings; one building
-- may have multiple vendors. The pair (building, vendor) is the natural key.
CREATE TABLE building_vendor (
    building_id           integer NOT NULL REFERENCES building(building_id),
    vendor_id             integer NOT NULL REFERENCES vendor_contact(vendor_id),
    vendor_account_number varchar,
    notes                 text,
    PRIMARY KEY (building_id, vendor_id)
);

-- Composite PK: one contract legitimately covers several buildings.
CREATE TABLE service_contract_building (
    contract_id integer NOT NULL REFERENCES service_contract(contract_id),
    building_id integer NOT NULL REFERENCES building(building_id),
    PRIMARY KEY (contract_id, building_id)
);

CREATE TABLE emergency_access_code (
    access_code_id  integer PRIMARY KEY,
    building_id     integer REFERENCES building(building_id), -- nullable: zone-level codes
    zone_name       varchar,
    code_type       varchar,
    code_value      varchar
);

CREATE TABLE building_paint_spec (
    paint_spec_id     integer PRIMARY KEY,
    building_id       integer NOT NULL REFERENCES building(building_id),
    zone              varchar,
    surface_label     varchar,
    product_interior  varchar,
    product_exterior  varchar,
    manufacturer      varchar
);

CREATE TABLE building_camera_system (
    camera_system_id  integer PRIMARY KEY,
    building_id       integer NOT NULL REFERENCES building(building_id),
    installed         access_status_enum,
    accessible_remote varchar,
    functional        varchar,
    platform          camera_platform,
    ip_domain         varchar,
    port              varchar,
    username          varchar,
    password          varchar
);

CREATE TABLE building_intercom (
    intercom_id               integer PRIMARY KEY,
    entrance_id               integer NOT NULL REFERENCES entrance(entrance_id),
    brand                     varchar,
    dyndns_address            varchar,
    panel_model               varchar,
    is_master_building        boolean,
    keyless_code_general      varchar,
    keyless_code_maintenance  varchar,
    keyless_code_tenant       varchar
);

CREATE TABLE building_access_control (
    access_control_id   integer PRIMARY KEY,
    building_id         integer NOT NULL REFERENCES building(building_id),
    brand               varchar,
    panel_type          varchar,
    connection_option   varchar,
    panel_serial_or_ip  varchar,
    ip_module_password  varchar,
    system_login        varchar,
    system_password     varchar
);

CREATE TABLE building_key_box (
    box_id                integer PRIMARY KEY,
    entrance_id           integer NOT NULL REFERENCES entrance(entrance_id),
    box_number_onsite     varchar,
    code                  varchar,
    location_description  text,
    keyless_intercom_code varchar,
    last_validated_date   date,
    last_validated_by     varchar
);

CREATE TABLE building_telecom (
    building_id                  integer PRIMARY KEY REFERENCES building(building_id),
    internet_provider            text,    -- ISP + account, combined (format too inconsistent to split)
    internet_broadcast_provider  text,    -- broadcast / cable internet provider + account
    tech_support_provider        text,    -- IT / tech support vendor + contact
    telephone_provider           text     -- telephone line provider + account (often multi-line for complexes)
);

CREATE TABLE pool_access_code (
    pool_code_id  integer PRIMARY KEY,
    building_id   integer REFERENCES building(building_id),  -- nullable: codes may be complex-wide
    code_value    varchar,
    notes         text
);

CREATE TABLE cleaning_task_checklist (
    checklist_id       integer PRIMARY KEY,
    building_id        integer NOT NULL REFERENCES building(building_id),
    format             varchar,             -- LEGACY: being superseded by format_type enum
    element            varchar,
    frequency_per_week numeric,
    hours_per_visit    numeric,
    season             varchar,
    total              numeric,
    freetext_content   text,                -- LEGACY: see raw_content
    format_type        checklist_format_type,
    raw_content        text                 -- fallback for day_rotation/single_line/freetext rows
);

-- Composite PK: one employee assigned to one building at most once per row.
CREATE TABLE building_employee_assignment (
    building_id          integer NOT NULL REFERENCES building(building_id),
    employee_id          integer NOT NULL REFERENCES employee(employee_id),
    weekly_hours_summer  numeric,
    weekly_hours_winter  numeric,
    access_notes         text,
    PRIMARY KEY (building_id, employee_id)
);

-- building_id is nullable: laundry contracts use their own 7th naming system,
-- confirmed still unreconciled — FK may not resolve for all rows.
CREATE TABLE laundry_contract (
    uln                        varchar PRIMARY KEY,
    building_id                integer REFERENCES building(building_id),
    payment_type               payment_type,
    contract_expiry            date,
    suite_count                integer,
    suite_to_set_ratio         integer,
    washer_count               integer,
    dryer_count                integer,
    wash_rate                  numeric,
    dry_rate                   numeric,
    loads_per_suite_pmpd       numeric,
    collections_pmpd           numeric,
    pay_rule_type              pay_rule_type,
    pay_rule_pct               numeric,
    min_commission             numeric,
    monthly_rental_fee         numeric,
    revenue_month              numeric,
    commission_month           numeric,
    commission_pct_month       numeric,
    revenue_per_set_month      numeric,
    commission_per_set_month   numeric,
    revenue_per_suite_month    numeric,
    commission_per_suite_month numeric
);

CREATE TABLE staff_shift (
    shift_id    integer PRIMARY KEY,
    employee_id integer NOT NULL REFERENCES employee(employee_id),
    shift_type  shift_type,
    start_date  date,
    end_date    date
);

CREATE TABLE on_call_schedule (
    on_call_id  integer PRIMARY KEY,
    employee_id integer NOT NULL REFERENCES employee(employee_id),
    start_date  date,
    end_date    date,
    swap_notes  text
);

CREATE TABLE waste_collection_schedule (
    schedule_id           integer PRIMARY KEY,
    building_id           integer NOT NULL REFERENCES building(building_id),
    collection_days       varchar,
    instructions_text     text,
    embedded_access_code  varchar
);

CREATE TABLE recurring_task_pattern (
    pattern_id            integer PRIMARY KEY,
    building_id           integer NOT NULL REFERENCES building(building_id),
    assigned_employee_id  integer NOT NULL REFERENCES employee(employee_id),
    task_type             varchar,
    recurrence_rule       varchar,
    standing_instructions text
);


-- ── Level 3 ───────────────────────────────────────────────────────────────────

-- building_id and unit_id are both nullable: equipment can be building-level
-- OR unit-level. At least one should be set; enforce via CHECK if needed later.
-- 18 fields below from "00. Follow-Ups - Boilers and Furnaces.xlsx"; source has
-- parallel heating/DHW column blocks — ingestion splits each source row into 2
-- equipment rows (equipment_type = 'heating' or 'dhw'), one per circuit.
CREATE TABLE equipment (
    equipment_id             integer PRIMARY KEY,
    building_id              integer REFERENCES building(building_id),
    unit_id                  integer REFERENCES unit(unit_id),
    equipment_type           equipment_type,
    make                     varchar,
    model                    varchar,
    install_year             integer,
    seasonal_shutdown_date   date,
    seasonal_restart_date    date,
    maintained_by_vendor_id  integer REFERENCES vendor_contact(vendor_id),
    notes                    text,
    -- Boilers source expansion --
    criticality              varchar,
    assigned_vendor_id       integer REFERENCES vendor_contact(vendor_id),  -- nullable; "Entrepreneur attitré"
    maintenance_frequency    varchar,
    last_maintenance_date    date,
    next_maintenance_date    date,
    maintenance_status       varchar,
    maintenance_note         text,
    urgency                  varchar,
    action_priority          varchar,
    device_condition         varchar,
    replacement_priority     varchar,
    service_area             varchar,  -- "desserte"
    component                varchar,  -- "composante"
    quantity                 integer,
    power                    varchar,  -- "puissance"; varchar — units vary (kW, BTU, HP, etc.)
    efficiency               varchar,
    power_source             varchar,  -- "alimentation"
    energy_supplier          varchar
);

CREATE TABLE lease (
    lease_id                       integer PRIMARY KEY,
    unit_id                        integer NOT NULL REFERENCES unit(unit_id),
    mois                           date,
    debut_bail                     date,
    fin_bail                       date,
    date_fin_confirmee             date,
    date_limite_preavis            date,
    statut                         varchar,
    langue_bail                    varchar,
    droit_animaux                  boolean,
    depot                          numeric,
    loyer_de_base                  numeric,
    loyer_total                    numeric,
    mode_paiement_habituel         varchar,
    somme_due_restante             numeric,
    disponibilite_tableau_location varchar,
    notes_collecte                 text
);

CREATE TABLE tenant_equipment_loan (
    loan_id            integer PRIMARY KEY,
    unit_id            integer NOT NULL REFERENCES unit(unit_id),
    tenant_id          integer NOT NULL REFERENCES tenant(tenant_id),
    equipment_type     varchar,
    quantity           integer,
    status             loan_status,
    loan_start_date    date,
    expected_end_date  date,
    has_contract       boolean,
    notes              text,
    payment_status     varchar,
    payment_date       date,
    payment_amount     numeric
);

CREATE TABLE vacant_unit_task (
    task_id               integer PRIMARY KEY,
    unit_id               integer NOT NULL REFERENCES unit(unit_id),
    priority              integer,
    access_status         varchar,
    listing_status        varchar,
    promised_lease_date   date,
    lease_start_date      date,
    future_tenant_name    varchar,
    future_tenant_contact varchar,
    notes_free            text,
    internal_notes        text
);

CREATE TABLE elevator_reservation (
    reservation_id  integer PRIMARY KEY,
    building_id     integer NOT NULL REFERENCES building(building_id),
    elevator_label  varchar,
    date            date,
    unit_id         integer NOT NULL REFERENCES unit(unit_id),
    move_type       move_type,
    time_slot       time_slot,
    tenant_id       integer NOT NULL REFERENCES tenant(tenant_id),
    confirmed       boolean
);


-- Static per-building fire-system configuration. Source: "0 - Master Tableau
-- Protection Incendie.xlsx" — confirmed real and fully populated.
-- Distinct from service_visit (inspection EVENTS) — this table records WHAT IS
-- INSTALLED and its current status. Three vendor FKs are nullable because not
-- every building has all subsystems contracted separately.
CREATE TABLE building_fire_system (
    fire_system_id              integer PRIMARY KEY,
    building_id                 integer NOT NULL REFERENCES building(building_id),
    panel_brand_model           varchar,
    panel_control_status        varchar,
    emergency_panel_status      varchar,
    smoke_detector_status       varchar,
    sprinkler_status            varchar,
    sprinkler_vendor_id         integer REFERENCES vendor_contact(vendor_id),  -- nullable
    hose_status                 varchar,
    pressurization_pump_status  varchar,
    co2_status                  varchar,
    co2_vendor_id               integer REFERENCES vendor_contact(vendor_id),  -- nullable
    dossier_link                varchar,
    current_fire_vendor_id      integer REFERENCES vendor_contact(vendor_id),  -- nullable
    corrective_actions_date     date,
    piezzo_status               varchar,
    notes                       text
);


-- ── Level 4 ───────────────────────────────────────────────────────────────────

CREATE TABLE tenancy_record (
    tenancy_id        integer PRIMARY KEY,
    lease_id          integer NOT NULL REFERENCES lease(lease_id),
    tenant_id         integer NOT NULL REFERENCES tenant(tenant_id),
    capacite          tenancy_capacity,
    start_date        date,
    end_date          date,
    reason_for_change text
);

CREATE TABLE guarantor (
    guarantor_id  integer PRIMARY KEY,
    lease_id      integer NOT NULL REFERENCES lease(lease_id),
    tenant_id     integer NOT NULL REFERENCES tenant(tenant_id),
    notes         text
);

CREATE TABLE parking_assignment (
    parking_id     integer PRIMARY KEY,
    lease_id       integer NOT NULL REFERENCES lease(lease_id),
    mode           varchar,
    location_type  varchar,
    count          integer,
    cost           numeric
);

CREATE TABLE storage_assignment (
    storage_id  integer PRIMARY KEY,
    lease_id    integer NOT NULL REFERENCES lease(lease_id),
    mode        varchar,
    count       integer,
    cost        numeric
);

CREATE TABLE unit_appliance (
    unit_appliance_id  integer PRIMARY KEY,
    lease_id           integer NOT NULL REFERENCES lease(lease_id),
    item               varchar,
    included           boolean,
    responsibility     varchar
);

CREATE TABLE vacant_unit_task_item (
    item_id    integer PRIMARY KEY,
    task_id    integer NOT NULL REFERENCES vacant_unit_task(task_id),
    task_type  task_item_type,
    status     varchar,
    notes      text
);

CREATE TABLE pest_control_case (
    case_id              integer PRIMARY KEY,
    building_id          integer NOT NULL REFERENCES building(building_id),
    vendor_id            integer REFERENCES vendor_contact(vendor_id), -- nullable
    pest_type            varchar,
    first_reported_date  date,
    warranty_active      boolean,
    warranty_expiry_date date,
    notes                text
);

CREATE TABLE service_visit (
    visit_id        integer PRIMARY KEY,
    building_id     integer NOT NULL REFERENCES building(building_id),
    vendor_id       integer REFERENCES vendor_contact(vendor_id),    -- nullable
    equipment_id    integer REFERENCES equipment(equipment_id),      -- nullable
    visit_type      service_visit_type,
    due_date        date,
    completed_date  date,
    result          varchar,
    deficiencies    text,
    next_due_date   date
);

-- Self-referential FK (duplicate_of_request_id) is valid inline in Postgres.
-- The column is nullable, so no bootstrapping issue on first inserts.
CREATE TABLE maintenance_request (
    request_id               integer PRIMARY KEY,
    building_id              integer NOT NULL REFERENCES building(building_id),
    unit_id                  integer NOT NULL REFERENCES unit(unit_id),
    project_id               integer REFERENCES project(project_id),         -- nullable
    source_calendar          varchar,
    urgency_tier             urgency_tier,
    sector_id                integer REFERENCES sector(sector_id),            -- nullable
    equipment_id             integer REFERENCES equipment(equipment_id),      -- nullable
    banked_queue_date        date,
    triage_summary           text,
    delegable_status         delegable_status,
    delegable_notes          text,
    report_status            report_status,
    report_notes             text,
    duplicate_of_request_id  integer REFERENCES maintenance_request(request_id), -- nullable self-ref
    addition_to_request_id   integer REFERENCES maintenance_request(request_id), -- nullable self-ref; ADDITION verdict (Guide rule 12)
    synergy_request_ids      integer[],
    synergy_reason           text,
    unit_label               varchar,
    project_label            varchar,
    time_estimate_bucket     time_estimate_bucket,
    time_estimate_raw        varchar,
    complexity_tier          complexity_tier,
    vendor_id                integer REFERENCES vendor_contact(vendor_id),   -- nullable
    subcontractor_name       varchar,
    proposed_assignee        varchar,
    tenant_agreement_notes   text,
    other_notes              text,
    congestion_level         congestion_level,
    caller_tenant_id         integer REFERENCES tenant(tenant_id),           -- nullable
    caller_name              varchar,
    caller_phone             varchar,
    dispatched               boolean,
    work_performed           text,
    tenant_present           boolean,
    follow_up_expected       boolean,
    -- NEW (2026-10-09) — Triage schema additions
    status                   request_status NOT NULL,
    routing_rule             varchar,
    triage_started_at        timestamp,
    triage_model_version     varchar,
    CONSTRAINT mr_addition_not_self CHECK (addition_to_request_id != request_id)
);


-- NEW (2026-10-09) — one row per model call attempt, including rejected/errored ones.
-- Separate from data_provenance: provenance records WHERE a value came from;
-- this records WHAT the model was asked and WHAT it said.
CREATE TABLE triage_log (
    log_id            serial    PRIMARY KEY,
    request_id        integer   NOT NULL REFERENCES maintenance_request(request_id),
    attempted_at      timestamp NOT NULL,
    model_version     varchar,
    context_sent      jsonb,
    raw_response      text,
    validation_result varchar,
    validation_detail text,
    latency_ms        integer,
    input_tokens      integer,
    output_tokens     integer
);


-- ── Level 5 ───────────────────────────────────────────────────────────────────

CREATE TABLE maintenance_followup_entry (
    followup_id          integer PRIMARY KEY,
    request_id           integer NOT NULL REFERENCES maintenance_request(request_id),
    entry_text           text,
    entry_date           date,
    entered_by_initials  varchar
);

CREATE TABLE maintenance_attachment (
    attachment_id  integer PRIMARY KEY,
    request_id     integer NOT NULL REFERENCES maintenance_request(request_id),
    drive_file_id  varchar,
    file_type      varchar
);

-- Links a maintenance request to a prior ticket referenced in its historique_raw.
-- relation_type = 'prior_ticket' is the only value currently produced (from historique_raw URLs);
-- the column exists so other relation kinds can be added later.
CREATE TABLE maintenance_request_history (
    history_id              serial PRIMARY KEY,
    request_id              integer NOT NULL REFERENCES maintenance_request(request_id),
    referenced_request_id   integer NOT NULL REFERENCES maintenance_request(request_id),
    relation_type           varchar NOT NULL,
    UNIQUE (request_id, referenced_request_id, relation_type),
    CHECK (request_id != referenced_request_id)
);

-- source_turnover_id is nullable: only set when an informal calendar intake
-- entry is later matched to a formal maintenance_request ticket.
CREATE TABLE unit_turnover (
    turnover_id                   integer PRIMARY KEY,
    unit_id                       integer NOT NULL REFERENCES unit(unit_id),
    move_reason                   move_reason,
    lease_end_date                date,
    move_out_confirmed_date       date,
    assignment_desired_date       date,
    move_out_time                 time,
    move_out_email_sent_date      date,
    key_return_method             varchar,
    lease_start_date              date,
    move_in_confirmed_date        date,
    move_in_time                  time,
    move_in_email_sent_date       date,
    key_pickup_method             varchar,
    intercom_status               intercom_status,
    cleaning_status               varchar,
    parking_remote_status         varchar,
    internet_transfer_current     boolean,
    internet_transfer_new         boolean,
    parking_stall_current         varchar,
    parking_stall_new             varchar,
    furnished_status_current      varchar,
    furnished_status_new          varchar,
    incoming_tenant_id            integer REFERENCES tenant(tenant_id),
    outgoing_tenant_id            integer REFERENCES tenant(tenant_id),
    pre_departure_inspection_notes text,
    general_notes                 text,
    room_count                    varchar,
    mattress_size                 varchar,
    source_turnover_id            integer REFERENCES maintenance_request(request_id),
    incoming_tenant_name_raw      varchar,
    outgoing_tenant_name_raw      varchar,
    outgoing_fin_bail             date,
    outgoing_loyer                numeric
);


-- ── Level 6 ───────────────────────────────────────────────────────────────────

CREATE TABLE unit_turnover_furniture_item (
    furniture_item_id  integer PRIMARY KEY,
    turnover_id        integer NOT NULL REFERENCES unit_turnover(turnover_id),
    appliance_type     varchar,
    included_current   boolean,
    included_new       boolean
);

CREATE TABLE unit_turnover_settlement (
    settlement_id          integer PRIMARY KEY,
    turnover_id            integer NOT NULL REFERENCES unit_turnover(turnover_id),
    deposit_amount_owed    numeric,
    deposit_received       boolean,
    deposit_refund_status  varchar,
    amount_owed_by_tenant  numeric,
    tal_dossier_open       boolean,
    edl_received           boolean,
    edl_satisfactory       boolean,
    notes                  text
);


-- ════════════════════════════════════════════════════════════
-- COMMENTS
-- ════════════════════════════════════════════════════════════

-- building_fire_system
COMMENT ON TABLE building_fire_system IS
    'Source: "0 - Master Tableau Protection Incendie.xlsx" — confirmed real and fully populated. '
    'Static per-building fire-system configuration; distinct from service_visit which logs inspection events.';
COMMENT ON COLUMN building_fire_system.sprinkler_vendor_id IS
    'Nullable: vendor contracted for sprinkler system. Not all buildings have sprinklers.';
COMMENT ON COLUMN building_fire_system.co2_vendor_id IS
    'Nullable: vendor contracted for CO2 suppression. Not all buildings have CO2 systems.';
COMMENT ON COLUMN building_fire_system.current_fire_vendor_id IS
    'Nullable: primary fire-protection vendor currently under contract for this building.';

-- sector
COMMENT ON COLUMN sector.territoire IS
    'Broader geographic region (e.g. "QUÉBEC-EST"). Distinct from the narrower secteur/color_code '
    'concept sourced from File 3 (CONTACTS). Do not merge or assume these two hierarchies are the '
    'same thing — relationship to be reconciled once confirmed.';

-- building
COMMENT ON COLUMN building.boite_a_cle_ext IS
    'Kept for backward compat; new key-box detail lives on building_key_box, '
    'which will eventually hang off entrance rather than building directly.';
COMMENT ON COLUMN building.raw_fiche_technique IS
    'Raw JSONB from the fiches techniques translation pipeline (jsonb for queryability).';
COMMENT ON COLUMN building.legacy_code IS
    'A002–A112 cross-reference from the Fire Protection master table RÉF. tab. '
    'NOT a unique key: 31 A-codes map to 2 or more buildings because the fire-protection filing '
    'system uses a coarser project-level grain than our building table. '
    'Nullable (4 buildings have no A-code: 2 terrain parcels, Corail, Marais).';

-- building_document
COMMENT ON COLUMN building_document.category IS
    'Allowed values (not enforced by constraint): elevator_contract / fire_protection / '
    'paint_spec / install_guide / plumbing_reference / other';

-- building_vendor
COMMENT ON COLUMN building_vendor.vendor_account_number IS
    'Confirmed NOT strictly 1:1 — one vendor account number can cover multiple buildings.';

-- building_camera_system — SENSITIVE
COMMENT ON COLUMN building_camera_system.password IS
    'SENSITIVE — encrypt at rest and restrict column-level access before deploying to '
    'production. Flag for encryption-at-rest and access-control review.';

-- building_access_control — SENSITIVE
COMMENT ON COLUMN building_access_control.ip_module_password IS
    'SENSITIVE — encrypt at rest and restrict column-level access before deploying to '
    'production. Flag for encryption-at-rest and access-control review.';
COMMENT ON COLUMN building_access_control.system_login IS
    'SENSITIVE — encrypt at rest and restrict column-level access before deploying to '
    'production. Flag for encryption-at-rest and access-control review.';
COMMENT ON COLUMN building_access_control.system_password IS
    'SENSITIVE — encrypt at rest and restrict column-level access before deploying to '
    'production. Flag for encryption-at-rest and access-control review.';

-- building_intercom
COMMENT ON COLUMN building_intercom.brand IS 'Known values: Mircom, Akuvox';

-- building_access_control
COMMENT ON COLUMN building_access_control.brand IS 'Known values: Paradox, Akuvox';

-- entrance
COMMENT ON TABLE entrance IS
    'No source file exists yet. Until real per-entrance data is captured, ingestion '
    'should create exactly one synthetic entrance per building (copying '
    'building.adresse/ville/code_postal) so building_intercom and building_key_box '
    'always have somewhere valid to point.';

-- unit
COMMENT ON COLUMN unit.unit_id IS
    'Natural key = Numéro unique d''unité in the source system.';

-- equipment
COMMENT ON COLUMN equipment.building_id IS
    'Nullable: set when this is building-level equipment. '
    'At least one of building_id or unit_id must be set.';
COMMENT ON COLUMN equipment.unit_id IS
    'Nullable: set when this is unit-level equipment (e.g. an apartment''s own heat pump). '
    'Single-table consolidation for both levels per live-map design — confirm against real '
    'data once a source exists. No source file exists yet.';
COMMENT ON COLUMN equipment.maintained_by_vendor_id IS
    'Nullable: vendor who maintains this piece of equipment. Not always known.';
COMMENT ON COLUMN equipment.assigned_vendor_id IS
    'Nullable: "Entrepreneur attitré" from Boilers source. Primary vendor assigned to this equipment.';
COMMENT ON COLUMN equipment.service_area IS
    '"Desserte" from Boilers source — geographic zone or building wing served by this equipment.';
COMMENT ON COLUMN equipment.component IS
    '"Composante" from Boilers source — sub-component or circuit identifier within the unit.';
COMMENT ON COLUMN equipment.power IS
    '"Puissance" — kept varchar; units vary across equipment types (kW, BTU, HP, etc.).';
COMMENT ON COLUMN equipment.power_source IS
    '"Alimentation" — energy feed type: electrical circuit, gas line, etc.';

-- cleaning_task_checklist
COMMENT ON COLUMN cleaning_task_checklist.format IS
    'LEGACY: free-text format string from original Ménage source. Superseded by format_type enum; '
    'retained for migration reference only.';
COMMENT ON COLUMN cleaning_task_checklist.freetext_content IS
    'LEGACY: unstructured note field from original source. Superseded by raw_content; '
    'retained for migration reference only.';
COMMENT ON COLUMN cleaning_task_checklist.format_type IS
    'NEW — checklist_format_type enum: structured | day_rotation | single_line | freetext. '
    'Source: Ménage cleaning sheets show 4 distinct layout patterns. Drives how raw_content is rendered.';
COMMENT ON COLUMN cleaning_task_checklist.raw_content IS
    'NEW — stores the full cell content for day_rotation, single_line, and freetext rows. '
    'Null for structured rows (element + frequency fields are the canonical representation).';

-- emergency_access_code
COMMENT ON COLUMN emergency_access_code.building_id IS
    'Nullable: some codes are zone-level, not building-level.';

-- laundry_contract
COMMENT ON COLUMN laundry_contract.building_id IS
    'Nullable: laundry contracts use their own address format (7th naming system in SIB) '
    '— confirmed still unreconciled per live map. FK may not resolve for all rows.';
COMMENT ON COLUMN laundry_contract.monthly_rental_fee IS
    'Only populated when pay_rule_type = ''rental''.';

-- vendor_category_exclusivity
COMMENT ON COLUMN vendor_category_exclusivity.rule_code IS
    'Allowed values: A0–A5';

-- waste_collection_schedule
COMMENT ON COLUMN waste_collection_schedule.embedded_access_code IS
    'Confirmed rare — 1 of 12 buildings sampled had a code embedded in collection instructions.';

-- maintenance_request
COMMENT ON COLUMN maintenance_request.source_calendar IS
    'Source calendar name. Known values: MAIN - Calls, MAIN - Calls ST Majordome Québec';

COMMENT ON COLUMN maintenance_request.project_label IS
    'Legacy fallback: raw project name for rows not yet matched to a project_id. '
    'Populated only when project_id is NULL.';
COMMENT ON COLUMN maintenance_request.subcontractor_name IS
    'Legacy fallback: typed-in vendor name for rows not yet matched to a vendor_id. '
    'Populated only when vendor_id is NULL.';
COMMENT ON COLUMN maintenance_request.proposed_assignee IS
    'Structurally always empty per Coordinator''s Guide rule 37 — confirmed 2026-09. '
    'Retained for schema fidelity; do not populate.';
COMMENT ON COLUMN maintenance_request.caller_name IS
    'Legacy fallback for unmatched or non-tenant callers '
    '(neighbours, family members, staff). Set when caller_tenant_id is NULL.';
COMMENT ON COLUMN maintenance_request.caller_phone IS
    'Legacy fallback for unmatched or non-tenant callers. Set when caller_tenant_id is NULL.';
COMMENT ON COLUMN maintenance_request.synergy_request_ids IS
    'Typed integer array of related request IDs (synergy group). Queryable with = ANY(synergy_request_ids).';

COMMENT ON COLUMN maintenance_request.status IS
    'Request lifecycle — see COMMENT ON TYPE request_status for full state descriptions. '
    'Lifecycle: intake_received → triage_pending → (triage_clarify | triage_proposal | triage_failed) → triaged → en_route → closed. '
    'All 10,565 rows ingested before 2026-10-09 carry ''closed'' as a backfill sentinel — it does not mean work was verified complete.';
COMMENT ON COLUMN maintenance_request.addition_to_request_id IS
    'ADDITION relation from Coordinator Guide rule 12 — a request that adds to an existing open ticket. '
    'Nullable; complement to duplicate_of_request_id (the DUPLICATE verdict). '
    'Self-reference forbidden: CONSTRAINT mr_addition_not_self CHECK (addition_to_request_id != request_id).';
COMMENT ON COLUMN maintenance_request.routing_rule IS
    'A0–A5 rule that produced the routing decision. Records WHICH rule fired; '
    'subcontractor_name records the decision itself. NULL for historical rows triaged before this app.';

-- triage_log
COMMENT ON TABLE triage_log IS
    'One row per model call attempt, including rejected and errored ones. '
    'A rejected row is the most interesting: it means a validation gate fired. '
    'Separate from data_provenance: provenance records WHERE a value came from; '
    'this records WHAT the model was asked and WHAT it said.';
COMMENT ON COLUMN triage_log.context_sent IS
    'Assembled user message sent to the model (JSONB). Enables exact reproduction of what the model saw.';
COMMENT ON COLUMN triage_log.raw_response IS
    'Verbatim model output, before validation or parsing.';
COMMENT ON COLUMN triage_log.validation_result IS
    'Outcome: accepted | rejected_<gate> | error | timeout. '
    'rejected_<gate> names the specific gate that fired (e.g. rejected_no_financial_terms).';
COMMENT ON COLUMN triage_log.validation_detail IS
    'Gate name, error message, or NULL for accepted responses.';

-- service_visit
COMMENT ON TABLE service_visit IS
    'No source file exists yet. Fire-protection folder holds ~106 per-building subfolders '
    'of unstructured inspection PDFs — nothing has been extracted into rows. '
    'The Service Call Log (IA) calendar-recurrence file may turn out to be a source here '
    '(still an open question — see recurring_task_pattern comment).';

-- service_contract
COMMENT ON TABLE service_contract IS
    'No source file exists yet (only unstructured year-by-year contract folders). '
    'One contract can legitimately cover several buildings via service_contract_building.';

-- pest_control_case
COMMENT ON TABLE pest_control_case IS
    'No source file exists yet. Extermination folder is near-empty with no structured tracking.';

-- tenancy_record
COMMENT ON TABLE tenancy_record IS
    'No source file exists yet. Can be backfilled approximately from Master Rent Roll '
    'snapshots (one row per tenant per lease, capacite = named_on_lease, '
    'start/end = lease dates) as a stopgap until a real collection process exists.';

-- guarantor
COMMENT ON TABLE guarantor IS
    'CAUTION: nom/telephone/courriel were REMOVED and replaced by tenant_id FK. '
    'This field-level change is inferred from map wording rather than a directly quoted '
    'field list — confirm before treating as final.';

-- building_paint_spec
COMMENT ON TABLE building_paint_spec IS
    'Real source confirmed: "0 - Charte des couleurs de peinture SIB" — distinct from '
    'the empty PEINTURE folder and from "Charte des couleurs SIB.xlsx". Not yet ingested.';

-- unit_turnover
COMMENT ON COLUMN unit_turnover.source_turnover_id IS
    'Optional FK linking an informal calendar intake entry to a formal maintenance_request ticket.';

-- recurring_task_pattern
COMMENT ON TABLE recurring_task_pattern IS
    'SOURCE: Coordinator''s Guide recurring-task rules — NOT the Service Call Log (IA) '
    'calendar-recurrence file. The Service Call Log''s actual mapping is still an open '
    'question; it may turn out to be a source for service_visit instead, which currently '
    'has no source at all.';

-- maintenance_attachment
COMMENT ON COLUMN maintenance_attachment.file_type IS
    'Known values: photo, video';

-- unit_turnover_furniture_item
COMMENT ON COLUMN unit_turnover_furniture_item.appliance_type IS
    'Known values: internet, cuisiniere, refrigerateur, lave-vaisselle, laveuse, secheuse';

-- ── data_provenance ───────────────────────────────────────────────────────────

CREATE TABLE data_provenance (
    provenance_id    integer PRIMARY KEY,
    target_table     varchar NOT NULL,
    target_pk        integer NOT NULL,
    target_column    varchar NOT NULL,
    source_type      varchar,
    source_drive_id  varchar,
    source_file_name varchar,
    source_tab       varchar,
    source_row       varchar,
    source_column    varchar,
    raw_value        text,
    ingested_value   text,
    ingested_at      timestamp
);

COMMENT ON TABLE data_provenance IS
    'One row per field per record for every ingestion script. Enables full field-level lineage tracing.';
COMMENT ON COLUMN data_provenance.target_table IS
    'Destination table name (e.g. ''building'')';
COMMENT ON COLUMN data_provenance.target_pk IS
    'Primary key value in the destination table';
COMMENT ON COLUMN data_provenance.target_column IS
    'Column name in the destination table';
COMMENT ON COLUMN data_provenance.source_type IS
    'Source category: FT (Fiches Techniques xlsx), MRR (Master Rent Roll xlsx), CROSSWALK';
COMMENT ON COLUMN data_provenance.source_drive_id IS
    'Google Drive file ID of the source file';
COMMENT ON COLUMN data_provenance.source_file_name IS
    'Human-readable filename of the source';
COMMENT ON COLUMN data_provenance.source_tab IS
    'Worksheet/tab name within the xlsx (null for single-sheet files)';
COMMENT ON COLUMN data_provenance.source_row IS
    '1-based row number or label within the source sheet';
COMMENT ON COLUMN data_provenance.source_column IS
    'Column reference within the source (letter or header name)';
COMMENT ON COLUMN data_provenance.raw_value IS
    'Exact value as read from the source, before any coercion';
COMMENT ON COLUMN data_provenance.ingested_value IS
    'Value as written to the destination column, after coercion/normalization';
COMMENT ON COLUMN data_provenance.ingested_at IS
    'UTC timestamp when this provenance row was written';
