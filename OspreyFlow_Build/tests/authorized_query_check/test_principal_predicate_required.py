"""Deterministic proof of `06_DECISIONS.md` ADR-041's own mechanical check
(`tools/authorized_query_check.py`): a `*_authorized` store method fails this check when its
principal predicate is removed from the query, and passes once it is filtered in the query itself
— the fetch-then-check shape `review.py`, `sites.py`, `investigations.py`, `studio_recipes.py`
and `pattern_store.py` each independently carried at one point (`06_DECISIONS.md` ADR-041's own
record has the full history).
"""

from __future__ import annotations

import sys

from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools"))

from authorized_query_check import CHECKED_DIR, check_source  # noqa: E402

_FETCH_THEN_CHECK = '''
class SiteStore:
    async def get(self, site_id: str) -> Site:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
        if row is None:
            raise SiteNotFoundError(site_id)
        return _row_to_site(row)

    async def get_authorized(self, site_id: str, principal: Principal) -> Site:
        site = await self.get(site_id)
        if site.owning_unit != principal.org_unit:
            raise SiteNotFoundError(site_id)
        return site
'''

_QUERY_SCOPED = '''
class SiteStore:
    async def get_authorized(self, site_id: str, principal: Principal) -> Site:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sites WHERE id = $1 AND owning_unit = $2",
                site_id,
                principal.org_unit,
            )
        if row is None:
            raise SiteNotFoundError(site_id)
        return _row_to_site(row)
'''


def test_a_principal_predicate_removed_from_the_query_is_flagged() -> None:
    violations = check_source("fixture.py", _FETCH_THEN_CHECK)
    assert len(violations) == 1
    assert "get_authorized" in violations[0]


def test_a_principal_predicate_filtered_in_the_query_itself_passes() -> None:
    assert check_source("fixture.py", _QUERY_SCOPED) == []


def test_a_module_level_route_dependency_with_no_self_is_not_flagged() -> None:
    # `app.py`'s `get_authorized_investigation`-shaped functions: named `*_authorized`, take a
    # `principal` parameter, delegate with no SQL of their own — legitimately not a store method.
    source = '''
async def get_authorized_investigation(
    investigation_id: str, principal: Principal
) -> Investigation:
    return await investigations.get_authorized(investigation_id, principal)
'''
    assert check_source("fixture.py", source) == []


def test_the_real_services_api_tree_has_no_offenders() -> None:
    violations: list[str] = []
    for path in sorted(CHECKED_DIR.glob("*.py")):
        violations.extend(check_source(str(path), path.read_text()))
    assert violations == [], f"unexpected authorized-query-check offenders: {violations}"


# ADR-099 Amendment 3 joins a dataset clause onto these queries, so the SQL is one f-string, which
# Python builds from the adjacent literals. The check reads it as a query as it reads a plain one;
# a query in an f-string that binds no principal is still flagged.

_FSTRING_SCOPED = '''
class AlertStore:
    async def list_authorized(self, principal: Principal) -> list[Alert]:
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, owner_id "
                f"FROM alerts WHERE owner_id = $1{reach} ORDER BY created_at DESC",
                principal.id,
                *extra,
            )
        return rows
'''

_FSTRING_UNSCOPED = '''
class AlertStore:
    async def list_authorized(self, principal: Principal) -> list[Alert]:
        reach, extra = reach_clause(principal, 1)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT id FROM alerts WHERE true{reach}", *extra)
        return [r for r in rows if r["owner_id"] == principal.id]
'''


def test_a_query_built_as_an_f_string_that_binds_the_principal_passes() -> None:
    assert check_source("alerts.py", _FSTRING_SCOPED) == []


def test_a_query_built_as_an_f_string_that_binds_no_principal_is_flagged() -> None:
    assert len(check_source("alerts.py", _FSTRING_UNSCOPED)) == 1
