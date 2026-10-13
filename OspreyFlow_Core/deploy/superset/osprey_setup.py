"""Superset's OspreyFlow roles and service user (`06_DECISIONS.md` ADR-111 Amendment 3), run by
`osprey_entrypoint.py` at every start — idempotent.

- `OspreyEmbedded`, the guest role a Glass viewer's token carries: Superset's read-only Gamma, plus
  reading the reporting mart's schema and nothing else.
- `OspreyEmbedder`, the role of the service user the Conduit signs in as: the same, plus granting a
  guest token and marking a dashboard embeddable. Its password is `SUPERSET_EMBEDDER_PASSWORD`, a
  deployment secret; the user is local to Superset and never a person.
"""

import os

from superset.app import create_app

MART_DATABASE, MART_SCHEMA = "OspreyFlow reports", "osprey_reports"
GUEST, EMBEDDER_ROLE, EMBEDDER = "OspreyEmbedded", "OspreyEmbedder", "osprey-embedder"

app = create_app()
with app.app_context():
    from superset import db
    from superset import security_manager as sm

    def unique(perms):  # Gamma already holds some of what is added; a role holds each once
        return list({p.id: p for p in perms}.values())

    from superset.models.core import Database

    gamma = sm.find_role("Gamma")
    # Superset's own name for the schema permission — since 4.1 it includes the catalog
    # ("[db].[catalog].[schema]"); a name written by hand without it matched no chart.
    database = db.session.query(Database).filter_by(database_name=MART_DATABASE).one()
    schema_perm = sm.get_schema_perm(
        database.database_name, database.get_default_catalog(), MART_SCHEMA
    )
    mart = sm.add_permission_view_menu("schema_access", schema_perm)
    guest = sm.find_role(GUEST) or sm.add_role(GUEST)
    guest.permissions = unique([*gamma.permissions, mart])
    extra = [sm.add_permission_view_menu(p, v) for p, v in (
        ("can_grant_guest_token", "SecurityRestApi"), ("can_set_embedded", "Dashboard"),
        ("can_read", "Dashboard"))]  # fmt: skip
    embedder_role = sm.find_role(EMBEDDER_ROLE) or sm.add_role(EMBEDDER_ROLE)
    embedder_role.permissions = unique([*gamma.permissions, mart, *extra])
    password = os.environ["SUPERSET_EMBEDDER_PASSWORD"]
    user = sm.find_user(username=EMBEDDER)
    if user is None:
        sm.add_user(EMBEDDER, "OspreyFlow", "embedder", f"{EMBEDDER}@ospreyflow.invalid",
                    embedder_role, password=password)  # fmt: skip
    else:
        user.roles = [embedder_role]
        sm.reset_password(user.id, password)
    # ADR-111 Amendment 4: a board drawn before a palette change forgets the old colours.
    import json
    import os.path

    from osprey_palette import forget_stale_label_colours
    from superset.models.dashboard import Dashboard

    with open(os.path.join(os.path.dirname(__file__), "pythonpath", "osprey_theme.json")) as themes:
        palette = json.load(themes)["categorical"]["colors"]
    refreshed = 0
    for dashboard in db.session.query(Dashboard).all():
        changed = forget_stale_label_colours(dashboard.json_metadata, palette)
        if changed is not None:
            dashboard.json_metadata = changed
            refreshed += 1
    db.session.commit()
    print(f"osprey_setup: roles and embedder in place; {refreshed} board(s) recoloured")
