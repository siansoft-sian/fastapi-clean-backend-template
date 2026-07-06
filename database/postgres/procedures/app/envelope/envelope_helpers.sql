-- Functions: app.ok(jsonb), app.error(text, text, jsonb)
-- Purpose: the standard {success, data, error, meta} envelope every app.*
--          function returns. `meta` stays {} at the DB layer; the API layer
--          adds request-scoped meta (request_id, path, ...).

CREATE OR REPLACE FUNCTION app.ok(p_data jsonb DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql IMMUTABLE AS
$$
SELECT jsonb_build_object(
    'success', true,
    'data', coalesce(p_data, 'null'::jsonb),
    'error', null,
    'meta', '{}'::jsonb
)
$$;

CREATE OR REPLACE FUNCTION app.error(p_code text, p_message text, p_details jsonb DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql IMMUTABLE AS
$$
SELECT jsonb_build_object(
    'success', false,
    'data', null,
    'error', jsonb_build_object(
        'code', p_code,
        'message', p_message,
        'details', coalesce(p_details, '{}'::jsonb)
    ),
    'meta', '{}'::jsonb
)
$$;
