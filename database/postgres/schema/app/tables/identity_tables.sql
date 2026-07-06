-- Tables: app.tenants, app.users, app.identities, app.memberships
-- Purpose: the MINIMUM surface app.map_identity needs. The full identity /
--          RBAC / tenancy model (roles, invitations, RLS policies, email
--          uniqueness) is a separate milestone — see DESIGN-sessions-identity.md.

CREATE TABLE app.tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.identities (
    provider text NOT NULL,
    subject text NOT NULL,
    user_id uuid NOT NULL REFERENCES app.users (id) ON DELETE CASCADE,
    email text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject)
);

CREATE INDEX identities_user_id_idx ON app.identities (user_id);

CREATE TABLE app.memberships (
    user_id uuid NOT NULL REFERENCES app.users (id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES app.tenants (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, tenant_id)
);

CREATE INDEX memberships_tenant_id_idx ON app.memberships (tenant_id);
