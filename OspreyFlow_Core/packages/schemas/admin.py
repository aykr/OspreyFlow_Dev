"""The Admin area's shapes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people and their roles,
and dashboard identities. Generated into TypeScript for the Glass's Admin area."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ingest import RunMetering
from .rights import Right


class PersonAccount(BaseModel):
    id: str
    username: str
    name: str
    enabled: bool
    roles: list[str]
    clearance: str | None = None
    org_unit: str | None = None
    email: str | None = None
    receivable_handling_codes: list[str] = Field(default_factory=list)
    #: Invited or reset, and not yet signed in to choose their own password.
    must_set_password: bool = False
    #: An account OspreyFlow itself uses (the deploy's verify probes), not a person's: never
    #: removed or joined to an organisation account (ADR-112 Amendment 3).
    system_account: bool = False
    #: Joined to an account at the organisation's identity provider: signing in through the
    #: organisation lands here (ADR-112 Amendment 3 (b)).
    organisation_linked: bool = False
    #: Has signed in at least once (ADR-148 Amendment 8): on Entra ID, a person added by object id
    #: has not, and counts for nothing a sign-in proves (the lock-out's last manager among them).
    #: Always true on Keycloak, whose accounts are the directory's own.
    signed_in: bool = True
    #: On Entra ID, when this person's clearance, unit and handling codes were last read from their
    #: token (ADR-148 Amendment 8); older than a day, they are not trusted to receive anything. None
    #: on Keycloak, whose directory attributes are current.
    access_read_at: datetime | None = None


#: A sign-in name the identity provider takes (measured: spaces and most punctuation are refused).
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,62}$"
#: Enough to catch a slip; whether the address works is the mail server's to say.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class AccessInput(BaseModel):
    """What a person may see (ADR-114 Amendment 5): clearance, unit and the handling codes they may
    receive — none above the administrator's own."""

    clearance: str = Field(min_length=1, max_length=40)
    org_unit: str = Field(min_length=1, max_length=60)
    receivable_handling_codes: list[str] = Field(default_factory=list)

    @field_validator("receivable_handling_codes")
    @classmethod
    def _few_codes(cls, codes: list[str]) -> list[str]:
        # A bound, kept out of the field so the generated type stays a plain array.
        if len(codes) > 16:
            raise ValueError("at most 16 handling codes")
        return codes


class PersonAccessInput(BaseModel):
    """Access for a person already here (`PUT /v1/admin/people/{id}/access`). On Keycloak, clearance
    and unit, and the codes (none when not given), as `AccessInput`. On Entra ID with the
    administrator fallback (ADR-148 Amendment 15), only the values this deployment sets: one not
    given is left as it is, and a value Entra sends is never given here."""

    clearance: str | None = Field(default=None, min_length=1, max_length=40)
    org_unit: str | None = Field(default=None, min_length=1, max_length=60)
    receivable_handling_codes: list[str] | None = None

    @field_validator("receivable_handling_codes")
    @classmethod
    def _few_codes(cls, codes: list[str] | None) -> list[str] | None:
        if codes is not None and len(codes) > 16:
            raise ValueError("at most 16 handling codes")
        return codes


class InviteInput(AccessInput):
    """A new person (ADR-114 Amendment 5): signed in by an emailed link when the deployment has a
    mail server, else by a one-time code shown once to the administrator."""

    username: str = Field(pattern=USERNAME_PATTERN)
    first_name: str = Field(default="", max_length=60)
    last_name: str = Field(default="", max_length=60)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)
    roles: list[str] = Field(default_factory=list, max_length=64)


class OrganisationArrival(BaseModel):
    """Someone the organisation's sign-in refused because an OspreyFlow account already holds their
    email address (ADR-114 Amendment 33, "Step 28 (e)"), not yet joined to any account — read from
    the identity provider's record of the refusal (ADR-112 Amendment 3 (b))."""

    #: The organisation's own id for the person (its tokens' `sub`): what a join is made with.
    subject: str
    #: Their name at the organisation (its tokens' `preferred_username`); empty when it gave none.
    provider_username: str
    last_refused: datetime
    #: How many times they were refused while the identity provider keeps its record (seven days).
    attempts: int


class OrganisationLinkInput(BaseModel):
    """`POST /v1/admin/people/{user_id}/organisation-link`: the refused arrival to join to this
    account, by the organisation's id for them (an `OrganisationArrival`'s `subject`)."""

    subject: str = Field(min_length=1, max_length=255)


class SignInDelivery(BaseModel):
    """How the person signs in next: by the identity provider's own emailed link, or by the one-time
    code in this answer — shown once, never stored by OspreyFlow, changed at first sign-in."""

    person: PersonAccount
    delivery: Literal["email", "one_time_code"]
    one_time_code: str | None = None


class DashboardIdentity(BaseModel):
    client_id: str
    #: The identity's account id — what a case Author grants Viewer to.
    account_id: str
    #: Its name, a slug: on Keycloak what follows `osprey-dashboard-` in its client id; on Entra ID
    #: the name it was registered by, one a tenant (ADR-148 Amendment 10). Superset's embedding
    #: matches a board on it.
    name: str | None = None
    clearance: str | None = None
    org_unit: str | None = None
    #: The handling codes the identity may receive — a viewer of its embedded board must hold
    #: every one (ADR-111 Amendment 3).
    receivable_handling_codes: list[str] = Field(default_factory=list)
    #: From the reporting mart (ADR-111 Amendment 2): when `report-sync` last truly pulled for this
    #: dashboard, its standing failure in words and when, and how many cases it pulls. Absent —
    #: never pulled — when reporting is off or the dashboard has no case yet.
    last_pulled: datetime | None = None
    last_failure: str | None = None
    failed_at: datetime | None = None
    cases_pulled: int = 0


class RegisteredDashboard(BaseModel):
    dashboard: DashboardIdentity
    #: Shown once, at registration; OspreyFlow keeps no copy. None on Entra ID (ADR-148 Amendment
    #: 10), where the identity's own app registration holds its secret.
    secret: str | None = None


class RolesInput(BaseModel):
    """A person's roles, set whole: the four roles, `right:<name>` grants, the old role names."""

    roles: list[str] = Field(max_length=64)


class SignInKind(BaseModel):
    """`GET /v1/admin/sign-in`: how this deployment's people sign in (ADR-148 Amendment 8), so Admin
    › People offers what it can do: invite on Keycloak; add by object id on Entra ID, where Entra
    holds the accounts."""

    kind: Literal["keycloak", "entra"]
    #: ADR-148 Amendment 15: on Entra ID, the values Admin › People sets here (the poc shape's
    #: fallback); none means Entra sends every one, and Access is not offered.
    administrator_sets: list[Literal["clearance", "org_unit", "handling_codes"]] = Field(
        default_factory=list
    )


class AddPersonInput(BaseModel):
    """A person added to Admin › People by their Entra object id, ahead of their first sign-in
    (ADR-148 Amendment 8). Only on Entra ID sign-in; Graph gives the object id."""

    object_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="The person's Entra object id, in lower case",
    )


class DashboardInput(BaseModel):
    """A dashboard identity to register: a name, and the clearance and unit it reads with — no
    higher than the registering administrator's own clearance."""

    name: str = Field(min_length=1, max_length=60)
    clearance: str = Field(min_length=1)
    org_unit: str = Field(min_length=1)
    #: ADR-148 Amendment 10: on Entra ID, the identity's own app registration's application id
    #: (required there; refused on Keycloak, where OspreyFlow creates the client).
    application_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="On Entra ID: the dashboard's app registration's application id, lower case",
    )


class ComponentHealth(BaseModel):
    """One part of the running deployment, asked just now: whether it answered, and how fast."""

    name: str
    ok: bool
    millis: int = Field(ge=0)
    detail: str | None = None
    #: What to do about it, in words, shown in place of "not answering" (ADR-114 Amendment 36):
    #: a part that answered and is wrong is not a part that did not answer.
    notice: str | None = None


class ModelRoleStatus(BaseModel):
    """One model role and where it runs (ADR-114 decision 11, Amendment 6)."""

    role: Literal["extraction", "vision", "transcription", "embedding"]
    #: The model the role uses for material that may be sent; the local one otherwise.
    model: str
    #: "this deployment", or the client's provider by name.
    runs_at: str
    local_model: str | None = None


class EngineStatus(BaseModel):
    """One model engine as the Admin area's System screen shows it (ADR-135 decision 5): its models,
    the roles it is the default for, and whether its key is present — never the key."""

    #: `local`, or the provider's name.
    name: str
    label: str
    #: Each role it has a model for, with the model.
    models: dict[str, str]
    #: The roles `osprey.yaml` names it the default for (a default with no key runs locally).
    default_for: list[str]
    #: Always true for `local`; for a provider, whether `deployment.env` holds its key.
    key_present: bool
    #: ADR-136 decision 1: the deployment's organisation holds a data-processing agreement with the
    #: provider covering this key. Always false for `local`, which sends nothing anywhere.
    privacy_contract: bool = False
    #: The agreement's reference, in words — never a secret.
    contract_reference: str | None = None


#: ADR-136 decision 2: where a dataset's material may go. `none` (the default): never to a hosted
#: engine; `contracted`: only to a provider marked `privacy_contract: true`; `any`: to any enabled
#: provider. The handling code must still be sendable.
DatasetEgress = Literal["none", "contracted", "any"]

#: ADR-145 Amendment 4 decision 6: the kinds Admin › Datasets shows (*Source*, *Composite*,
#: *Drawn*).
AdminDatasetKind = Literal["source", "composite", "drawn"]

#: ADR-145 decision 8: *Author promotes*, or *Second person reviews*.
PromotionPolicy = Literal["author_promotes", "second_person_reviews"]


class AdminDataset(BaseModel):
    """One dataset as the Admin area's Datasets screen shows it (ADR-136 decision 2): its name, the
    unit that holds it, and its egress."""

    id: str
    name: str
    owning_unit: str
    egress: DatasetEgress
    #: The highest marking the dataset may hold (ADR-145 decision 8, Amendment 3; ADR-143 Amendment
    #: 2 decision 3). Set when the dataset is made: a drawn dataset's maker chooses it within their
    #: own clearance; every other dataset has the deployment's highest marking, which the Conduit
    #: fills in (L3.1b step 5); `None` until then, read as that. Read by the Glass's Admin ›
    #: Datasets column *Highest marking it may hold* (L2.4 part 2); enforced on what is written
    #: into the dataset and its cases' layers by L3.3.
    highest_marking: str | None = None
    #: ADR-145 Amendment 4 decision 6: what kind of dataset this is. An analyst layer is never a
    #: row of its own; it is counted under the case it belongs to (`AdminLinkedCase`).
    kind: AdminDatasetKind = "source"
    #: ADR-145 decision 8: how a drawn item is promoted into the dataset. Enforced by the
    #: promotion itself (L3.4); set here, audited.
    promotion_policy: PromotionPolicy = "author_promotes"


class DatasetPromotionPolicyInput(BaseModel):
    """`PUT /v1/admin/datasets/{dataset_id}/promotion-policy`: an administrator's change,
    audited."""

    model_config = ConfigDict(extra="forbid")

    promotion_policy: PromotionPolicy


class DatasetAuthor(BaseModel):
    """One of a dataset's Authors, as Admin › Datasets shows them: the account and its name."""

    id: str
    #: The directory's name for the account; `None` when the directory has none to give.
    name: str | None = None
    #: Holds `review_promotions` (ADR-112 Amendment 4), so may approve another's promotion when
    #: the policy is *Second person reviews*.
    approves: bool = False


class AdminDatasetAuthors(BaseModel):
    """A dataset's Authors (ADR-145 Amendment 4 decision 3): its home case's Authors. Names and
    accounts only, never the home case's contents."""

    dataset_id: str
    #: `False` until the dataset's first *Make live* made its home case, which names the first
    #: Authors; *Change owner…* changes them after that.
    has_home_case: bool
    people: list[DatasetAuthor] = Field(default_factory=list)
    #: A team (ADR-112 Amendment 5), when teams are built; `None` until then.
    team: str | None = None


class AdminLinkedCase(BaseModel):
    """One case linked to a dataset, as an administrator sees it (ADR-143 Amendment 2 decision 2):
    its name, its state and its layer as counts. Never the layer's contents: no item, label or
    property (rule 7). An open and a removed case carry exactly the same fields."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    name: str
    state: Literal["open", "removed"]
    #: The dataset's own home case (ADR-145 Amendment 4 decision 2).
    home_case: bool = False
    #: The composite the case reads this dataset through; `None` when it chose this dataset.
    through: str | None = None
    #: The layer's live items and links, counted by the graph store.
    items: int = Field(ge=0)
    links: int = Field(ge=0)
    #: The bytes the layer holds: its items' and links' stored properties and their pictures,
    #: counted by the stores (the owner's ruling of 8 November 2026, Q1 (a)).
    size_bytes: int = Field(ge=0)


class AdminDatasetCases(BaseModel):
    dataset_id: str
    cases: list[AdminLinkedCase]


#: ADR-143 Amendment 2 decision 1: what may happen to a removed case's layer.
LayerAction = Literal["merge", "delete"]


class LayerDryRun(BaseModel):
    """A removed case's *Merge into the dataset* or *Delete*, run dry: what it would touch, in
    counts, and nothing written. The action itself is the promotion's (L3.4)."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    action: LayerAction
    items: int = Field(ge=0)
    links: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    #: What the action would do, in words.
    would: str


class DatasetEgressInput(BaseModel):
    """`PUT /v1/admin/datasets/{dataset_id}/egress`: an administrator's change, audited."""

    egress: DatasetEgress


class UpdateNotice(BaseModel):
    """The last `ospreyflow update --check` (ADR-114 Amendment 8 point 2), as it wrote it."""

    current: str
    checked_at: str
    latest: str | None
    update_available: bool
    #: The release's changelog section.
    notes: str | None
    url: str | None
    #: Why the check could not answer, in words; then nothing is offered.
    problem: str | None


class ConvertedViews(BaseModel):
    """ADR-144 decision 6 on *Admin › System*: how many cases made from another became views, in how
    many cases; the migration's dry-run report names any it did not place. Counted in the
    administrator's own unit only (rule 7)."""

    views: int = 0
    cases: int = 0
    #: Said in words when the count could not be read, so the screen never draws nothing for it.
    problem: str | None = None


class SystemStatus(BaseModel):
    """The Admin area's *System* screen (ADR-110 Amendment 1): each component, asked as the screen
    opens — what the harness's preflight showed before launch, for a running deployment."""

    version: str | None = None
    components: list[ComponentHealth]
    #: ADR-114 decision 11: each role's model and where it runs; never a key.
    models: list[ModelRoleStatus] = Field(default_factory=list)
    #: ADR-135: each engine, its defaults, and whether its key is present; never a key.
    engines: list[EngineStatus] = Field(default_factory=list)
    #: Said whenever a role runs at the client's provider: what case content leaves, and to whom.
    model_notice: str | None = None
    #: ADR-114 Amendment 8: the last update check; none when there has been none.
    update: UpdateNotice | None = None
    #: ADR-144 decision 6: what the migration made of cases made from another, in the
    #: administrator's own unit; none when the case views' store is not reachable.
    converted_views: ConvertedViews | None = None
    #: ADR-148 decision 10: the highest marking this deployment may hold; a load or an import marked
    #: above it is refused. None only from a Conduit that predates the setting.
    highest_marking: str | None = None


class EmbeddedDashboard(BaseModel):
    """A Superset dashboard this person may open inside the Glass (ADR-111 Amendment 3)."""

    slug: str
    title: str


class DashboardGuestToken(BaseModel):
    """A short-lived, read-only Superset guest token for one embedded dashboard."""

    token: str
    #: The dashboard's embedded id, which the Glass's SDK mounts.
    uuid: str
    #: Where the browser reaches Superset.
    superset_origin: str


class DemoPackStatus(BaseModel):
    """A demo pack as the Admin area shows it (ADR-114 Amendment 5, "Show and explain"): what it
    shows, its licence and credit, whether it is loaded — only in a case the administrator can open
    — and the command that adds it on the host. The Conduit never runs it."""

    id: str
    title: str
    shows: str
    delivery: Literal["seed", "download"]
    licence: str
    attribution: str | None = None
    case_name: str
    loaded_case_id: str | None = None
    command: str
    source_page: str | None = None
    size_bytes: int | None = None
    #: Real people's data, not generated (ADR-114 Amendment 23 point 4): said wherever it is listed.
    real_data: bool = False


class ScheduleRunView(BaseModel):
    """One row of the run ledger as the Admin area shows it (ADR-110 decisions 6 and 8). Where the
    reader may not view the source, `withheld` is set and the counts and the failure's words are
    left out: a count of what a load wrote is a read (rule 3)."""

    run_id: str
    trigger: Literal["manual", "schedule", "watch", "release", "source_refresh", "external"]
    slot: datetime | None = None
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["running", "succeeded", "failed", "refused", "blocked", "skipped", "missed"]
    run_as: str
    withheld: bool = False
    rows_read: int | None = None
    nodes_created: int | None = None
    nodes_referenced: int | None = None
    edges_created: int | None = None
    rows_rejected: int | None = None
    rows_held: int | None = None
    load_id: str | None = None
    failure: str | None = None
    #: ADR-110 Amendment 4: the name of the file a watched run took; withheld like the counts.
    file: str | None = None
    #: ADR-110 Amendment 6 point 9: what the run cost; withheld like the counts.
    metering: RunMetering | None = None


class AdminSchedule(BaseModel):
    """A scheduled recipe in the Admin area's *Schedules and runs* (ADR-110 decision 8)."""

    recipe_id: str
    label: str
    case_id: str | None = None
    #: `None` for a recipe run only by its folder watch.
    cron: str | None = None
    #: ADR-110 Amendment 4: the filename pattern its dataset's folder is watched for.
    watch: str | None = None
    timezone: str
    #: The schedule in words: "every weekday at 06:00 (Europe/London)", and the watch's.
    schedule: str
    owner: str | None = None
    next_run: datetime | None = None
    paused: bool = False
    paused_reason: str | None = None
    #: The ontology changed since it was published: due slots are blocked until it is again.
    flagged: bool = False
    last_run: ScheduleRunView | None = None


class DataFeed(BaseModel):
    """A pipeline feeding a case's datasets, as the Glass's *Data feeds* shows it (ADR-110
    decision 9): how fresh the case's data is. `schedule` is `None` for a recipe run only by
    hand."""

    recipe_id: str
    label: str
    schedule: str | None = None
    next_run: datetime | None = None
    paused: bool = False
    flagged: bool = False
    last_run: ScheduleRunView | None = None


class ChangeScheduleInput(BaseModel):
    """The Admin area's *Change schedule* (ADR-110 Amendment 3): a new time, the owner kept."""

    cron: str
    timezone: str | None = None


class PauseScheduleInput(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# --- Roles, teams and Disable (ADR-145 decisions 6-7, Amendments 4 and 5; ADR-112 Amendments 4 and
# 5; ADR-146 Amendment 1) ------------------------------------------------------------------------


class BuiltInRole(BaseModel):
    """A built-in role or the *Super user* preset (ADR-145 decision 7): listed with its rights,
    copied into a custom role, never edited. A preset is given as the roles it names."""

    id: str
    label: str
    rights: list[Right]
    #: The roles the preset gives together (`SUPER_USER_PRESET`); empty for a role.
    gives: list[str] = Field(default_factory=list)


class TeamInput(BaseModel):
    """*Make this role a team* (ADR-112 Amendment 5 decision 3): a display name and a contact
    mailbox, a distribution list that is a contact, never a sign-in."""

    display_name: str = Field(min_length=1, max_length=80)
    mailbox: str = Field(pattern=EMAIL_PATTERN, max_length=254)


class TeamMember(BaseModel):
    id: str
    name: str | None = None


class Team(BaseModel):
    """A team: a custom role's holders (the owner's L2.5 Q4 (a)), its lead, and a cover until a
    date. `acting_lead` is the cover while the cover lasts, else the lead: the shape ADR-146
    Amendment 1's queue tools read (rules' L2.10, `services/api/teams.py::acting_lead`)."""

    role_id: str
    display_name: str
    mailbox: str
    lead: str | None = None
    cover: str | None = None
    #: The last day the cover acts (inclusive); after it, the lead acts again with no action.
    cover_until: date | None = None
    acting_lead: str | None = None
    members: list[TeamMember] = Field(default_factory=list)


class CustomRoleInput(BaseModel):
    """A custom role (ADR-112 Amendment 4): a name and a set of existing rights. Refused at the
    route: a name already used, no rights, a right the giver does not hold, a forbidden pair
    (ADR-145 decision 7), and a change that leaves no enabled person holding `manage_people`
    (ADR-145 Amendment 5)."""

    name: str = Field(min_length=1, max_length=60)
    rights: list[str] = Field(max_length=64)


class CustomRoleVersion(BaseModel):
    version: int
    name: str
    rights: list[Right]
    changed_by: str
    changed_at: datetime


class CustomRole(BaseModel):
    """A custom role's current version, held in the token as `role:<id>`."""

    id: str
    name: str
    version: int
    rights: list[Right]
    changed_by: str
    changed_at: datetime
    #: How many people hold it now.
    holders: int = 0
    team: Team | None = None


class RolesCatalogue(BaseModel):
    """`GET /v1/admin/roles`: the built-in roles, the preset and every custom role."""

    built_in: list[BuiltInRole]
    custom: list[CustomRole]


class TeamLeadInput(BaseModel):
    """Name a team's lead, or hand the role over (ADR-112 Amendment 5 decision 4): a member."""

    lead: str = Field(min_length=1, max_length=200)


class TeamCoverInput(BaseModel):
    """Name a cover until a date (inclusive), a member other than the lead; `cover: null` ends
    it."""

    cover: str | None = Field(default=None, min_length=1, max_length=200)
    until: date | None = None


OwnedKind = Literal[
    "case_author", "home_case_author", "team_lead", "hotlist", "monitor", "saved_pattern",
    "typology_rule", "pipeline_schedule", "list_schedule",
    # L2.5b: the kinds L3.8's ownership route reads (`person_ownership.py`, ADR-145 Amendment 8).
    "view", "board", "link_type_proposal", "drawn_watch",
]


class OwnedItem(BaseModel):
    """One thing a person answers for, as *Disable…* lists it (ADR-145 decision 6): each needs a
    *Transfer to…* before *Transfer and disable* is accepted."""

    kind: OwnedKind
    id: str
    #: What it is, in words ("Kestrel (case)"), only what the administrator may already see.
    label: str
    #: The case a view, a board, a proposed type or a watch is in (L3.8's items); none otherwise.
    investigation_id: str | None = None
    #: The marking its recipient must clear (ADR-145 Amendment 9): a view's or a board's case's
    #: highest, a proposal's or a watch's dataset's; *Transfer to…* offers only people who do.
    needs_clearance: str | None = None


class DisablePlan(BaseModel):
    """`GET /v1/admin/people/{user_id}/disable-plan`: everything the person owns today, and the
    kinds not yet listed because their owner route is not built (L2.5b, L3.8's ownership route)."""

    person: str
    items: list[OwnedItem]
    not_yet_listed: list[str] = Field(default_factory=list)


class OwnedTransfer(BaseModel):
    kind: OwnedKind
    id: str
    to: str = Field(min_length=1, max_length=200)


class DisableInput(BaseModel):
    """*Transfer and disable*: a recipient for every item of the plan; refused, in words, while any
    item has none (409 `untransferred`), nothing changed."""

    transfers: list[OwnedTransfer] = Field(default_factory=list, max_length=2000)


class PersonCaseLevel(BaseModel):
    """One of a person's case levels, as their row says it (R3): "Author of Kestrel"; `through`
    names the team that gives it, when a team does."""

    investigation_id: str
    name: str
    level: Literal["viewer", "editor", "author"]
    through: str | None = None


class AdminPersonRow(BaseModel):
    """`GET /v1/admin/people/rows` (R3): each person's case levels and the cases with no Author
    (R1), only of cases in the administrator's own unit (ADR-052)."""

    id: str
    levels: list[PersonCaseLevel] = Field(default_factory=list)


class CaseWithoutAuthor(BaseModel):
    investigation_id: str
    name: str


class AdminPeopleRows(BaseModel):
    rows: list[AdminPersonRow]
    without_author: list[CaseWithoutAuthor]


#: ADR-145 decision 10 (O2): which record an Audit entry is held in. `case_and_admin` is the audit
#: stream every route writes (`audit_log`: the case audit, the people, roles and dataset audits, and
#: loads); `rules` the case's rule audit (ADR-109 ruling 1, read as its own read withholds it);
#: `models` the engines' history (ADR-112 Amendment 7 decision 7).
AuditRecord = Literal["case_and_admin", "rules", "models"]
#: Decision 10's kinds, with the rule audit's and the engines' history as kinds of their own, and
#: every other action (reads, refusals) as `reads_and_other`.
AuditKind = Literal[
    "assertions", "loads_and_promotions", "types", "people_and_roles", "datasets", "rules",
    "models", "reads_and_other",
]  # fmt: skip


class AuditSectionEntry(BaseModel):
    """One entry of Admin › Audit, read under the reader's own principal (rule 3). `detail` holds
    the entry's words only where the reader's own read of that record would show them; otherwise it
    is null and `words_withheld` says so, and the entry's count is withheld with them."""

    recorded_at: datetime
    #: Who acted, by name, or fixed words where the identity provider gives none: never an
    #: account's id (rule 7, ADR-106 Amendment 1).
    who: str
    action: str
    kind: AuditKind
    held_in: AuditRecord
    investigation_id: str | None = None
    case_name: str | None = None
    detail: dict[str, Any] | None = None
    words_withheld: bool = False
    result_cardinality: int | None = None


class AuditSectionPage(BaseModel):
    """`GET /v1/admin/audit`: a page, newest first, with the total of what this reader may see under
    these filters. An entry withheld from them is neither on the page nor in the total."""

    entries: list[AuditSectionEntry] = Field(default_factory=list)
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    #: What this record leaves out and why, said rather than left silent (rule 2).
    note: str | None = None
    #: The person picker's choices: the names of everyone who wrote an entry of this record the
    #: reader may read, whatever the other filters; a filter by person sends one of these back.
    people: list[str] = Field(default_factory=list)


class PromotionAlertSetting(BaseModel):
    """Admin › Operations' *Alert the reviewers and administrators after N days* (ADR-145
    decision 9; default 3)."""

    model_config = ConfigDict(extra="forbid")

    alert_after_days: int = Field(default=3, ge=1, le=90)


class AgeingRule(BaseModel):
    """One thing that ages in Operations (O3), and what happens when it does, in words."""

    what: str
    after_days: int
    then: str


class WaitingPromotion(BaseModel):
    """A promotion waiting for review (ADR-143 decision 10), as Operations lists it: named by its
    load and dataset, never by what it adds (rule 7)."""

    promotion_id: str
    load_id: str
    dataset_id: str
    dataset_name: str
    #: The proposer by name, or fixed words where there is none: never an account's id (rule 7).
    proposed_by_name: str
    proposed_at: datetime
    age_days: int = Field(ge=0)
    overdue: bool


class OperationsAgeing(BaseModel):
    """`GET /v1/admin/operations/ageing`: what ages and when, and the promotions waiting."""

    alert_after_days: int
    rules: list[AgeingRule]
    waiting: list[WaitingPromotion] = Field(default_factory=list)
    #: False until promotions are recorded (case's L3.4): none can wait, and the screen says so.
    promotions_recorded: bool = False


class PromotionOverdueAlert(BaseModel):
    """*Promotions overdue* (ADR-145 Amendment 4 decision 11, R7), raised once per promotion at N
    days to the dataset's Authors holding `review_promotions` and to administrators. Its words name
    the load and the dataset, never the promotion's contents (rule 7)."""

    promotion_id: str
    load_id: str
    dataset_id: str
    raised_at: datetime
    recipients: list[str]
    words: str


class PromotionOverdueNotice(BaseModel):
    """One *Promotions overdue* alert as its recipient reads it (L2.7's *Needs you*): the alert
    without its recipients, since who else was alerted is not that person's to read."""

    promotion_id: str
    load_id: str
    dataset_id: str
    raised_at: datetime
    words: str


class NeedsYouProposals(BaseModel):
    """One dataset's proposed link types in the reader's *Needs you* (ADR-145 decision 11, A2;
    ADR-090 Amendment 4): how many the reader may read and decide. A dataset whose proposals the
    reader is not cleared to read is not listed at all, not even as having one open (ADR-143
    Amendment 4's *Open*, the strict reading; the orchestrator's ruling at L2.7's review)."""

    dataset_id: str
    dataset_name: str
    to_decide: int


class ScheduleNoticeEntry(BaseModel):
    """One scheduled load's notice in its owner's *Needs you* (ADR-110 Amendment 19): a run of their
    schedule that failed or was refused, in its own words. Only ever its owner's (the read is
    filtered by owner in the query); it names the recipe, never another person."""

    notice_id: str
    recipe_id: str
    raised_at: datetime
    words: str


class NeedsYou(BaseModel):
    """The reader's *Needs you* (L2.7): their overdue promotions, served only while they are still a
    recipient (Amendment 4 decision 11), and the proposed link types of the datasets their cases
    load into, for a holder of `accept_types`; and their own scheduled loads' notices of the last
    seven days, newest first, at most twenty with the total said (ADR-110 Amendment 19)."""

    promotions_overdue: list[PromotionOverdueNotice]
    proposals: list[NeedsYouProposals]
    schedule_notices: list[ScheduleNoticeEntry] = []
    #: How many of the reader's notices the window holds, the listed ones included: more than
    #: `schedule_notices` lists is said, never cut silently (rule 2).
    schedule_notices_total: int = 0


ALL_MODELS: list[type[BaseModel]] = [
    PersonAccount, DashboardIdentity, RegisteredDashboard, RolesInput, AddPersonInput,
    SignInKind, DashboardInput,
    ComponentHealth, UpdateNotice, ConvertedViews, SystemStatus, EmbeddedDashboard,
    DashboardGuestToken,
    AccessInput, PersonAccessInput, InviteInput, SignInDelivery, DemoPackStatus,
    ModelRoleStatus, EngineStatus, ScheduleRunView, AdminSchedule, PauseScheduleInput, DataFeed,
    ChangeScheduleInput, AdminDataset, DatasetEgressInput, OrganisationArrival,
    OrganisationLinkInput, DatasetPromotionPolicyInput, DatasetAuthor, AdminDatasetAuthors,
    AdminLinkedCase, AdminDatasetCases, LayerDryRun,
    BuiltInRole, TeamInput, TeamMember, Team, CustomRoleInput, CustomRoleVersion, CustomRole,
    RolesCatalogue, TeamLeadInput, TeamCoverInput, OwnedItem, DisablePlan, OwnedTransfer,
    DisableInput, PersonCaseLevel, AdminPersonRow, CaseWithoutAuthor, AdminPeopleRows,
    AuditSectionEntry, AuditSectionPage, PromotionAlertSetting, AgeingRule, WaitingPromotion,
    OperationsAgeing, PromotionOverdueAlert, PromotionOverdueNotice, NeedsYouProposals,
    ScheduleNoticeEntry, NeedsYou,
]  # fmt: skip
