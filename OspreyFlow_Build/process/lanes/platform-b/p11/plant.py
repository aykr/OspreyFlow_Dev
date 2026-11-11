"""P11 part 1's plants (rule 15), committed so a reviewer can run them again: each fault is planted at
its real call site (one exact replacement in one file), the tests that should catch it are run, and
the file is put back whatever happens. A plant whose tests stay green is reported `NOT RED`, and the
run exits 1.

Run from `OspreyFlow_Core`, offline (closed ports, no stack):

    env ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 \
        .venv/bin/python ../OspreyFlow_Build/process/lanes/platform-b/p11/plant.py [ID…]

Each plant's id is the red record's (`RED_RECORD.md`): 1-8 and A-L from the first round, as they now
stand; N1-N24 and U1-U3 from the orchestrator's review, round 1; R1-R6 from round 2 and its review
(carried into P11 part 2 by the confirmation); W1-W8 P11 part 2's own (the gateway by default and
its own identity). The R and W plants need `cloud-platform`'s files as on main after 2733de4, and
the W plants part 2's own changes to them.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

K = "../OspreyFlow_Build/tests/services/api/test_model_engine_kinds.py"
S = "../OspreyFlow_Build/tests/adapters/model_litellm/test_stand_in_engine_kinds.py"
C = "../OspreyFlow_Build/tests/cli/test_models_verb_iam_role.py"
H = "../OspreyFlow_Build/tests/harness/test_model_engines.py"
VITEST = "apps/workspace/src/admin/sections/Models.test.tsx"
#: Needs `shared-files-P11.diff` applied (the two registry ids), as the keyboard run does.
KEYBOARD = "apps/workspace/keyboard/admin-models.spec.ts"

ADMIN = "services/api/model_admin.py"
SCHEMA = "packages/schemas/deployment.py"
CONNECTION = "packages/adapters/model_litellm/connection.py"
STAND_IN = "packages/adapters/model_litellm/stand_in.py"
CLI_MODELS = "cli/ospreyflow/models.py"
CLI_MAIN = "cli/ospreyflow/main.py"
GLASS = "apps/workspace/src/admin/sections/Models.tsx"
CLOUD = "harness/cloud_platform/__init__.py"
TERRAFORM = "harness/cloud_platform/terraform.py"
G = "../OspreyFlow_Build/tests/harness/test_cloud_platform_gateway.py"
R = "../OspreyFlow_Build/tests/harness/test_cloud_platform_render.py"


@dataclass(frozen=True)
class Plant:
    id: str
    where: str
    fault: str
    file: str
    old: str
    new: str
    tests: tuple[str, ...]
    #: A `-k` expression narrowing the tests, where one file holds several.
    only: str | None = None

    def command(self) -> list[str]:
        if self.file.startswith("apps/") and self.tests == (VITEST,):
            return ["npx", "vitest", "run", VITEST]
        if self.tests == (KEYBOARD,):
            # platform-b's own Playwright slot (scripts/lane_ports.tsv), and the British date order
            # the usage case types in.
            return ["env", "OSPREY_PORTS_SLOT=7", "LANG=en_GB.UTF-8", "LC_ALL=en_GB.UTF-8",
                    "npx", "playwright", "test",
                    "--config", "apps/workspace/keyboard/playwright.config.ts", KEYBOARD,
                    "--reporter=line"]  # fmt: skip
        args = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q",
                "-p", "no:cacheprovider", "--tb=line", "-rf", *self.tests]  # fmt: skip
        return [*args, "-k", self.only] if self.only else args


PLANTS = [
    # --- the first round (P11 part 1 as built at e28c561), as each now stands --------------------
    Plant("1", "GatewayAdmin.add_entry", "every entry names a credential, IAM-role ones too", ADMIN,
          '        if not provider.keyless:\n            params["litellm_credential_name"]',
          '        if True:\n            params["litellm_credential_name"]',
          (f"{K}::test_an_iam_role_engine_keeps_no_key_anywhere",)),
    Plant("2", "ModelAdmin.set_key", "the IAM-role refusal removed", ADMIN,
          "            if any(p.name == name and p.keyless for p in current.providers):\n"
          "                # ADR-135 Amendment 4: no key is stored",
          "            if False:\n                # ADR-135 Amendment 4: no key is stored",
          (f"{K}::test_an_iam_role_engine_keeps_no_key_anywhere",)),
    Plant("3", "ModelAdmin.edit_engine", "an address change keeps the key (only guard left of "
          "`_where_the_key_goes`)", ADMIN,
          "            if (before.api_base or None) != (provider.api_base or None):",
          "            if False:",
          (f"{K}::test_a_refused_reconcile_after_an_address_change_says_no_key_rather_than_key_set",)),
    Plant("4", "model_keys.move_keys", "the CLI moves a key for an IAM-role engine",
          "services/api/model_keys.py",
          "enabled = {p.name for p in admin.settings.providers if not p.keyless}",
          "enabled = {p.name for p in admin.settings.providers}",
          (f"{K}::test_the_command_line_moves_no_key_for_an_iam_role_engine",)),
    Plant("5", "ModelAdmin.routes", "an IAM-role engine offered only with a key", ADMIN,
          'key_present=self.key_state(p.name) in ("set", "iam_role"),',
          'key_present=self.key_state(p.name) in ("set",),',
          (f"{K}::test_bedrock_answers_through_the_gateway_pod_s_role_in_london",)),
    Plant("6", "apply.provider_secret_lines", "the install asks every engine for a key",
          "harness/apply.py",
          "    # An engine signed in by the gateway's own IAM role keeps no key (ADR-135 Amendment 4).\n"
          "    for provider in config.models.keyed_providers:",
          "    for provider in config.models.enabled_providers:",
          (f"{K}::test_the_install_asks_no_key_for_an_iam_role_engine",)),
    Plant("7", "render.model_engines_env", "the kind not written", "harness/render.py",
          '**({} if p.plain else {"kind": p.kind, "auth": p.auth, "region": p.region}),',
          "**({}),",
          (f"{K}::test_the_render_tells_the_conduit_each_engine_s_kind_and_how_it_signs_in",)),
    Plant("8", "model_routing.routes_from_env", "the role ignored", "services/api/model_routing.py",
          'key_present=raw.get("auth") == "iam_role"\n', "key_present=False\n",
          (f"{K}::test_an_iam_role_engine_has_no_key_variable_and_is_offered_with_none",)),
    Plant("A", "cluster.render_cluster", "an IAM-role engine's held key not blanked",
          "harness/cluster.py", "    blanks = [*blanks, *keyless_blanks]", "    blanks = [*blanks]",
          (f"{K}::test_an_iam_role_engine_s_held_key_is_blanked_in_every_cluster_workload",)),
    Plant("B", "engine_refusal", "`bedrock` taken as a provider on cloud-platform", SCHEMA,
          '    if provider.name == "bedrock":\n        # LiteLLM routes',
          "    if False:\n        # LiteLLM routes",
          (K,), "refuses_each_shape and bedrock-named"),
    Plant("C", "engine_refusal", "the gateway by the role taken", SCHEMA,
          '    if provider.kind == "gateway" and provider.auth == "iam_role":', "    if False:",
          (K,), "refuses_each_shape and gateway-by-role-held"),
    Plant("D", "ModelAdmin.edit_engine", "the kind changeable", ADMIN,
          "            if before.kind != provider.kind:", "            if False:",
          (f"{K}::test_an_engine_s_kind_is_fixed_once_added_so_its_contract_never_moves_to_another",)),
    Plant("E", "ModelAdmin.remove_key", "removal not refused", ADMIN,
          "            if any(p.name == name and p.keyless for p in current.providers):\n"
          "                raise ModelAdminRefused(\n"
          '                    f"{name} signs in by the gateway\'s own IAM role and keeps no key; there',
          "            if False:\n"
          "                raise ModelAdminRefused(\n"
          '                    f"{name} signs in by the gateway\'s own IAM role and keeps no key; there',
          (f"{K}::test_an_iam_role_engine_keeps_no_key_anywhere",)),
    Plant("F", "ModelAdmin._start_once", "no entries for a declared IAM-role engine", ADMIN,
          "        if self._settings is None and not any(p.keyless for p in self._installed.providers):",
          "        if self._settings is None:",
          (K,), "declared"),
    Plant("G", "ModelAdmin.edit_engine", '"key set" kept after the credential went', ADMIN,
          '                self._save(current.model_copy(update={"keys": kept}, deep=True))',
          "                pass",
          (f"{K}::test_a_refused_reconcile_after_an_address_change_says_no_key_rather_than_key_set",)),
    Plant("H", "install_page._providers", "a key field offered for it", "harness/install_page.py",
          "        for p in models.keyed_providers", "        for p in models.enabled_providers",
          (f"{K}::test_the_install_page_offers_no_key_field_for_an_iam_role_engine",)),
    Plant("I", "connection.classify", "STS's refusal unread", CONNECTION,
          '    if "Unable to locate credentials" in body or "AssumeRoleWithWebIdentity" in body:',
          '    if "Unable to locate credentials" in body:',
          (f"{S}::test_bedrock_refuses_when_the_role_does_not_trust_the_gateway_s_service_account",)),
    Plant("J", "connection.classify", "the inference-profile refusal unread", CONNECTION,
          '        "model identifier is invalid" in body or "on-demand throughput isn" in body',
          '        "model identifier is invalid" in body',
          (f"{S}::test_bedrock_refuses_a_model_offered_only_through_an_inference_profile",)),
    Plant("K", "ospreyflow.models._STATE_WORDS", "`iam_role` unknown to the CLI", CLI_MODELS,
          '    "iam_role": "none kept: signs in by the gateway\'s own IAM role",\n', "",
          (f"{C}::test_an_iam_role_engine_is_listed_as_keeping_no_key",)),
    Plant("L", "ospreyflow.main._models", "`models key`/`remove-key` not refused first", CLI_MAIN,
          '    if args.action in ("key", "remove-key") and (states or {}).get(args.name) == "iam_role":',
          "    if False:",
          (C,), "refuse_an_iam_role_engine_before_reading"),
    # --- the orchestrator's review, round 1 -------------------------------------------------------
    Plant("N1", "engine_refusal", "off cloud-platform, the two kinds taken (item 1)", SCHEMA,
          "        if provider.plain:\n            return None\n        return (",
          "        return None\n        return (",
          (K,), "neither_offered_nor_taken"),
    Plant("N2", "engine_refusal", "Amendment 4's rules on every profile (the blocker, item 1)",
          SCHEMA, "    if profile not in MODEL_ROUTE_PROFILES:\n        if provider.plain:",
          "    if False:\n        if provider.plain:",
          (K,), "off_the_cloud_platform or loads_off_the_cloud_platform"),
    Plant("N3", "ModelSettingsFile.load", "the profile's refusal not read from the file", ADMIN,
          "        if refused := refused_on(settings.providers, self.profile):",
          "        if refused := None:",
          (f"{K}::test_the_conduit_refuses_a_cross_region_id_however_it_arrives",)),
    Plant("N4", "Installed.from_env", "the profile's refusal not read at start", ADMIN,
          '        if refused := refused_on(providers, environ.get("OSPREY_PROFILE", "")):',
          "        if refused := None:",
          (f"{K}::test_the_conduit_refuses_a_cross_region_id_however_it_arrives",)),
    Plant("N5", "ModelAdmin._validated", "Admin › Models ignores the profile", ADMIN,
          "        if refused := refused_on(settings.providers, self._file.profile):",
          "        if refused := None:",
          (K,), "refuses_each_shape or neither_offered_nor_taken"),
    Plant("N6", "OspreyConfig._engines_suit_the_profile", "osprey.yaml ignores the profile", SCHEMA,
          "            if refused := engine_refusal(provider, profile):",
          "            if refused := None:",
          (f"{K}::test_osprey_yaml_off_the_cloud_platform_profile_takes_bedrock_by_key_and_refuses_the_kinds",)),
    Plant("N7", "engine_refusal", "a cross-region inference profile's id taken (item 2)", SCHEMA,
          "            if not _BEDROCK_MODEL_ID.fullmatch(model):", "            if False:",
          (K,), "refuses_each_shape and (id- or arn-)"),
    Plant("N8", "_address_refusal", "a key before the host taken (item 4)", SCHEMA,
          '    if "@" in parts.netloc:', "    if False:",
          (f"{K}::test_a_planted_token_appears_in_no_response_log_audit_file_or_gateway_row",)),
    Plant("N9", "_address_refusal", "a key in the query or fragment taken (item 4)", SCHEMA,
          '    if parts.query or parts.fragment or "?" in address or "#" in address:',
          "    if False:",
          (f"{K}::test_a_planted_token_appears_in_no_response_log_audit_file_or_gateway_row",)),
    Plant("N10", "engine_refusal", "a key-shaped label taken (item 4)", SCHEMA,
          "    if provider.label and _label_looks_like_a_key(provider.label):", "    if False:",
          (f"{K}::test_a_planted_token_appears_in_no_response_log_audit_file_or_gateway_row",)),
    Plant("N11", "connection.classify", "Bedrock's model access read as the role refused (item 3)",
          CONNECTION, '    if "have access to the model with the specified model ID" in body:',
          "    if False:",
          (S, K), "model_the_account or model_not_enabled"),
    Plant("N12", "connection.classify", "Bedrock's expired credentials read as the role refused "
          "(item 3)", CONNECTION, '    if "ExpiredToken" in body or (', "    if False and (",
          (S, K), "expired or expiry"),
    Plant("N13", "KIND_WORDS", "the gateway's 403 said as the token alone (item 3)", ADMIN,
          '    ("gateway", "key_refused"): (', '    ("gateway_", "key_refused"): (',
          (f"{K}::test_the_gateway_s_policy_refusal_names_the_policy_as_well_as_the_token",)),
    Plant("N14", "ModelAdmin.test", "the gateway's other-shaped 4xx said as unreachable (item 3)",
          ADMIN, '                outcome = "request_refused"', "                pass",
          (K,), "another_shape"),
    Plant("N15", "the stand-in", "the address matched only as written (item 3)", STAND_IN,
          '        address = (params.get("api_base") or "").rstrip("/")',
          '        address = params.get("api_base") or ""',
          (S, K), "trailing_slash"),
    Plant("N16", "ospreyflow.main._models", "a key read with the Conduit silent (item 8)",
          CLI_MAIN, "        and states is None\n        and engine_keys.may_sign_in_by_role(",
          "        and False\n        and engine_keys.may_sign_in_by_role(",
          (C,), "conduit_silent_no_key"),
    Plant("N17", "ospreyflow.models.may_sign_in_by_role", "an engine added in Admin › Models not "
          "held back on cloud-platform (item 8)", CLI_MODELS,
          '    if config.get("profile") == MODEL_ROUTE_PROFILE:\n        return True',
          "    if False:\n        return True",
          (C,), "conduit_silent_no_key and added"),
    Plant("N18", "ModelAdmin.view", "the two kinds offered on every profile (item 1)", ADMIN,
          "            engine_kinds=engine_kinds_offered(self._file.profile),",
          '            engine_kinds=engine_kinds_offered("cloud-platform"),',
          (K,), "neither_offered_nor_taken or as_before"),
    Plant("N19", "ModelSettingsFile.save", "a plain provider's file written with the new fields",
          ADMIN, '        dumped["providers"] = [plain_dump(p) for p in settings.providers]',
          "        pass",
          (f"{K}::test_off_the_cloud_platform_profile_the_models_file_and_render_are_written_as_before",)),
    Plant("N20", "render.model_engines_env", "a plain provider's line written with the new fields",
          "harness/render.py",
          '**({} if p.plain else {"kind": p.kind, "auth": p.auth, "region": p.region}),',
          '**{"kind": p.kind, "auth": p.auth, "region": p.region},',
          (f"{H}::test_the_conduit_is_told_the_engines_the_defaults_and_key_presence_never_a_key",)),
    Plant("N21", "ospreyflow.models.MODEL_ROUTE_PROFILE", "the CLI's profile drifts from the "
          "schema's", CLI_MODELS, 'MODEL_ROUTE_PROFILE = "cloud-platform"',
          'MODEL_ROUTE_PROFILE = "cloud_platform"',
          (f"{C}::test_the_command_line_names_the_profile_as_the_schema_does",)),
    Plant("N22", "the stand-in", "Bedrock grants a model the account was not given (item 3)",
          STAND_IN,
          "        if upstream.enabled_models is not None and model not in upstream.enabled_models:",
          "        if False:",
          (S,), "model_the_account"),
    # N23 first planted in `render_cluster`'s gateway branch, which never ran (the gateway has no
    # `envFrom`): NOT RED, and the branch was dead code, now removed. Planted again where a key
    # really arrives: the gateway service's own environment, which the cluster translates.
    Plant("N23", "render.compose_services (litellm)", "a static AWS key named for the gateway "
          "(item 8)", "harness/render.py",
          '            "LITELLM_LOCAL_MODEL_COST_MAP": "True",\n',
          '            "LITELLM_LOCAL_MODEL_COST_MAP": "True",\n'
          '            "AWS_ACCESS_KEY_ID": "${AWS_ACCESS_KEY_ID:-}",\n',
          (K,), "static_aws_key"),
    Plant("N25", "render.compose_services (litellm)", "the gateway handed the whole deployment.env, "
          "a static AWS key in it unnamed (item 8)", "harness/render.py",
          '        "volumes": ["./litellm.yaml:/app/config.yaml:ro"],\n',
          '        "volumes": ["./litellm.yaml:/app/config.yaml:ro"],\n'
          '        "env_file": ["deployment.env"],\n',
          (K,), "static_aws_key"),
    Plant("N24", "ModelAdmin.add_engine", "a plain provider's audit names the new fields", ADMIN,
          "        named = [f for f in _EDITABLE if not (provider.plain and f in _KIND_FIELDS)]",
          "        named = list(_EDITABLE)",
          (f"{K}::test_off_the_cloud_platform_profile_the_models_file_and_render_are_written_as_before",)),
    # --- the Glass (vitest) -----------------------------------------------------------------------
    Plant("U1", "Models.tsx EngineForm", "the kind offered on every profile (item 1)", GLASS,
          '  const offersKinds = kinds.length > 1 || draft.kind !== "provider";',
          "  const offersKinds = true;", (VITEST,)),
    Plant("U2", "Models.tsx EngineForm", "`bedrock` offered as a provider by a key on cloud-platform",
          GLASS, 'PROVIDERS.filter((p) => p !== "bedrock" || !kinds.includes("bedrock"))',
          "PROVIDERS", (VITEST,)),
    Plant("U3", "Models.tsx providerOf", "a plain provider sent with the new fields", GLASS,
          '...(draft.kind === "provider" ? {} : { kind: draft.kind, auth: authFor(draft.kind) }),',
          "...{ kind: draft.kind, auth: authFor(draft.kind) },", (VITEST,)),
    # --- the keyboard walkthrough (rule 13; the review's item 8: the body, not only the POST) -----
    Plant("U4", "Models.tsx providerOf", "the gateway added without its address", GLASS,
          '    api_base: draft.kind === "bedrock" ? null : draft.api_base.trim() || null,',
          "    api_base: null,", (KEYBOARD,)),
    Plant("U5", "Models.tsx providerOf", "an engine of the two kinds sent as a provider", GLASS,
          '...(draft.kind === "provider" ? {} : { kind: draft.kind, auth: authFor(draft.kind) }),',
          "...{},", (KEYBOARD,)),
    # --- round 2 and its review, carried into P11 part 2 (CARRIES: their reds were prose only) ----
    Plant("R1", "_a_key_in_the_path", "a token in one case (lower or upper hex, base32) taken",
          SCHEMA, 're.fullmatch(r"[a-z0-9]{24,}|[A-Z0-9]{24,}", segment)',
          're.fullmatch(r"(?!)", segment)', (K,), "never_echoed"),
    Plant("R2", "_label_looks_like_a_key", "a token among a label's or reference's words taken",
          SCHEMA, "    return _looks_like_a_key(text) or any(",
          "    return _looks_like_a_key(text) or False and any(", (K,), "never_echoed"),
    Plant("R3", "_JWT", "a padded or encoded JWT's dot not read", SCHEMA,
          '_DOT = r"=*(?:\\.|%2[eE])"', '_DOT = r"\\."', (K,), "never_echoed"),
    Plant("R4", "_JWT", "a JWE (its second part not `eyJ`) not read", SCHEMA,
          '_JWT = re.compile(rf"eyJ{_B64}{{8,}}{_DOT}{_B64}{{8,}}',
          '_JWT = re.compile(rf"eyJ{_B64}{{8,}}{_DOT}eyJ{_B64}{{8,}}', (K,), "never_echoed"),
    Plant("R5", "OspreyConfig._engines_suit_the_profile", "ENGINES_AS honoured on any profile",
          SCHEMA,
          "translated = engines_as == MODEL_ROUTE_PROFILE and self.profile is Profile.CLUSTER",
          "translated = engines_as == MODEL_ROUTE_PROFILE", (K,), "engines_as_context"),
    Plant("R6", "_egress_hosts", "a no-address engine's host found by its name, not its kind",
          CLOUD,
          "    if kind in profile.egress.engine_kind_hosts:\n"
          "        # A kind that names no address (Bedrock): by its kind, its region's (P11).\n"
          "        return profile.egress.engine_kind_hosts[kind]",
          "    if name in profile.egress.engine_kind_hosts:\n"
          "        # A kind that names no address (Bedrock): by its kind, its region's (P11).\n"
          "        return profile.egress.engine_kind_hosts[name]",
          (K,), "egress_host"),
    # --- P11 part 2: the gateway by default, and its own identity ---------------------------------
    Plant("W1", "render_cloud_platform", "the gateway only with an engine enabled at install", CLOUD,
          '    workloads = [w for w in values["workloads"] if w["name"] not in NOT_RENDERED]',
          '    workloads = [w for w in values["workloads"] if w["name"] not in NOT_RENDERED\n'
          '                 and (config.models.enabled_providers or w["name"] != "litellm")]',
          (G, R), "gateway_is_rendered"),
    # W2 planted with a host whose networks the test gives (Gemini's), so it is red on the egress
    # itself, not on the render's own refusal of a host with none (the orchestrator's round 1).
    Plant("W2", "_egress_hosts", "a model host allowed out with no engine enabled", CLOUD,
          "    hosts += engine_hosts(config, profile)",
          "    hosts += engine_hosts(config, profile)\n"
          '    hosts += [profile.egress.engine_hosts["gemini"]]',
          (G,), "no_model_host"),
    Plant("W3", "render_cloud_platform", "the gateway given no account of its own (the engine "
          "kinds' Bedrock cases red too: the stand-in's role is the render's)", CLOUD,
          '        if pod["name"] == "litellm" and bedrock_enabled(config):',
          '        if False and pod["name"] == "litellm":',
          (G, R, K)),
    Plant("W4", "_gateway_role", "the role's trust bound to the namespace's account", TERRAFORM,
          "    account = gateway_account(platform)",
          "    account = platform.secrets.irsa.service_account", (G,), "grants_bedrock"),
    Plant("W5", "_gateway_role", "an S3 action granted the gateway", TERRAFORM,
          "'[\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\"]'",
          "'[\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\", \"s3:GetObject\"]'",
          (G,), "grants_bedrock"),
    Plant("W6", "_gateway_role", "every region's models granted", TERRAFORM,
          '_q(f"arn:aws:bedrock:{r}::foundation-model/*")',
          '_q("arn:aws:bedrock:*::foundation-model/*")', (G,), "grants_bedrock"),
    Plant("W7", "render_terraform", "a gateway role made with no Bedrock engine", TERRAFORM,
          "    if bedrock_enabled(config):\n        files",
          "    if True:\n        files", (G,), "without_bedrock"),
    Plant("W8", "render_cloud_platform", "the gateway run as the namespace's own account", CLOUD,
          "            pod[\"serviceAccountName\"] = gateway_account(platform)",
          "            pod[\"serviceAccountName\"] = platform.secrets.irsa.service_account",
          (G, R, K)),
    # --- P11 part 2, round 1's fixes ---------------------------------------------------------------
    Plant("W9", "ModelAdmin._made_by_the_render", "an engine the render did not make enabled",
          ADMIN, "        if self._file.profile != MODEL_ROUTE_PROFILE:\n            return",
          "        if True:\n            return", (K,), "render_did_not or host_the_render"),
    Plant("W10", "gateway_account", "Bedrock rendered with no gateway account named", CLOUD,
          "    if not account:\n        raise CloudPlatformNotRenderable(",
          "    if False:\n        raise CloudPlatformNotRenderable(", (G,), "naming_no_gateway"),
    Plant("W11", "IrsaSettings", "one account for both, or a name Kubernetes refuses",
          "harness/cloud_platform/settings.py",
          "        if self.gateway_service_account == self.service_account:",
          "        return self\n        if self.gateway_service_account == self.service_account:",
          (G,), "kubernetes_name"),
    Plant("W12", "ModelProviderConfig._reference_is_words", "the reference's word-by-word check "
          "on every profile", SCHEMA, "        if _looks_like_a_key(cleaned):",
          "        if _label_looks_like_a_key(cleaned):", (K,), "long_reference"),
    # --- P11 part 2, round 2: an engine from the models file the render did not make ---------------
    Plant("W13", "ModelAdmin._hosted", "a restored engine the render did not make written into "
          "the gateway", ADMIN,
          "        made = [p for p in settings.providers if self._not_made(p) is None]",
          "        made = list(settings.providers)", (K,), "restored_engine or no_word_from"),
    Plant("W14", "ModelAdmin.routes", "an engine the render did not make offered to analysts", ADMIN,
          "            if self._not_made(p) is None  # never offered unless the render made its way out",
          "            if True", (K,), "restored_engine or no_word_from"),
    Plant("W15", "ModelAdmin.set_key", "a key written for an engine the render did not make", ADMIN,
          "            if refused := self._not_made(next(p for p in current.providers if p.name == name)):\n"
          "                raise ModelAdminRefused(refused)  # never written into the gateway (round 2)\n"
          "            if any(p.name == name and p.keyless",
          "            if any(p.name == name and p.keyless", (K,), "restored_engine"),
]


def _forget_bytecode(path: Path) -> None:
    """Python trusts a `.pyc` whose source has the same size and mtime (to the second): a plant of
    the same length, put back within the second, would leave the planted bytecode to run in every
    later test (found 11 November: N21's `cloud_platform` outlived its own run). So none is written
    while a plant runs, and any for the planted file is removed when it is put back."""
    for cached in path.parent.glob(f"__pycache__/{path.stem}.*.pyc"):
        cached.unlink(missing_ok=True)


def run(plant: Plant) -> tuple[bool, str]:
    path = Path(plant.file)
    original = path.read_text(encoding="utf-8")
    if original.count(plant.old) != 1:
        return False, f"the planted line is in {plant.file} {original.count(plant.old)} times, not once"
    environ = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        _forget_bytecode(path)
        path.write_text(original.replace(plant.old, plant.new), encoding="utf-8")
        done = subprocess.run(
            plant.command(), capture_output=True, text=True, check=False, env=environ
        )
    finally:
        path.write_text(original, encoding="utf-8")
        _forget_bytecode(path)
    out = done.stdout + done.stderr
    failed = [line for line in out.splitlines()
              if line.startswith(("FAILED", "E  ", " FAIL ", "  ×", " ×")) or "AssertionError" in line
              or re.match(r"\s+\d+\) .+ › ", line) or "toMatchObject" in line]  # fmt: skip
    summary = next((line for line in reversed(out.splitlines()) if line.strip()), "")
    return done.returncode != 0, "\n      ".join([summary, *dict.fromkeys(failed)])


def main(wanted: list[str]) -> int:
    chosen = [p for p in PLANTS if not wanted or p.id in wanted]
    not_red = []
    for plant in chosen:
        red, said = run(plant)
        print(f"{plant.id:>4}  {'RED' if red else 'NOT RED'}  {plant.where}: {plant.fault}\n      {said}")
        if not red:
            not_red.append(plant.id)
    print(f"\n{len(chosen) - len(not_red)} of {len(chosen)} plants red"
          + (f"; NOT RED: {', '.join(not_red)}" if not_red else ""))
    return 1 if not_red else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
