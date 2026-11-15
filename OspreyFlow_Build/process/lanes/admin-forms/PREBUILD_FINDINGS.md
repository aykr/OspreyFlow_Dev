# Admin forms: what the owner needs to know before the build

The owner's prompt is `OWNER_PROMPT_2026-11-15.md` and their rulings are `OWNER_RULINGS_2026-11-15.md`. This is
rules-b's research of 15 November 2026, on `lane/rules-b-admin-forms-research` from main 8f598d3 (the rulings at
5407f96). It is research only: no product code was changed and nothing joins v0.5.2. No stack, server, browser or
desktop app was used.

How each claim is sourced:

- **Code** is cited as a path and line on main 8f598d3. Paths start at `OspreyFlow_Core/` unless they begin with
  `spec/` or `tests/`, which are under `OspreyFlow_Build/`.
- **Providers' documents** are cited by URL with the quoted words, fetched on 15 November 2026.
- **Search-engine snippets.** Some quotes came only from these, not from the page itself. Each one is marked
  "(snippet; page not read)" and needs a person to read the page before the list ships (section 7).

## 0. Read this first

1. **Half of the model form is already built.** ADR-135 Amendment 2 (8 November) reversed "never in the Admin area":
   "**It reverses ADR-135's ruling 2** ("never in the Admin area, never in a browser page of the Glass")"
   (`spec/06_DECISIONS.md:29284-29285`). It was built: *Admin › Models* takes a key write-only, puts it in the model
   gateway's own database and restarts nothing (`services/api/model_admin.py:430-440`;
   `apps/workspace/src/admin/sections/Models.tsx:249-254`). Three things are not built:
   - the provider list;
   - checking before adding;
   - listing the models a key may use.

   The administration guide was never brought into line with Amendment 2. It still says a key is "kept in
   `deployment.env` alone … never shown in the Admin area or any page of the Glass"
   (`spec/10_ADMINISTRATION_GUIDE.md:2607-2609`), and that `models key` "restarts the model gateway"
   (`spec/10_ADMINISTRATION_GUIDE.md:2019`). The code says "Nothing is restarted" (`cli/ospreyflow/models.py:5-10`).
   So the ADR-135 amendment drafted here (§5.3) mostly adds the checks and the list, and its guide change is a
   correction.
2. **Ruling 7 is already the rule.** Amendment 2 decision 4 says: "**it passes through the Conduit's key route and is
   kept by nothing but the gateway's database**" (`spec/06_DECISIONS.md:29421-29423`). What is new is that checking
   before adding puts the key in the gateway before the engine exists (§5.1).
3. **Ruling 5 applies to a store that is already sealed, and to one that is not.**
   - Model keys are already sealed by LiteLLM under the deployment's salt (`harness/render.py:228-238`).
   - The map key file is plain YAML at mode 600: `"key": r.key.get_secret_value()`
     (`services/api/map_admin.py:193-198`).
   - Spec 05 §6.1 still binds both: "**A backup carries no secrets. A restore re-mints them. Nothing in a backup may
     ever be encrypted with a deployment-scoped key.**" (`spec/05_DEPLOYMENT.md:1167-1168`).

   So an encrypted key file stays out of every backup, and a restore asks for each key again (§5.2).
4. **Five things to raise with the orchestrator, not designed around** (§8):
   - MapTiler under ruling 2;
   - a possible plain-text map key file in today's cloud-platform backup;
   - rotating the model salt;
   - Bedrock listing needing more IAM;
   - Ordnance Survey's and Esri's terms not yet read in full.

## 1. Each profile: where each key is kept, and how a change is picked up

The profiles are `local-lite`, `small`, `cluster` and `cloud-platform` (`packages/schemas/deployment.py:72-78`;
`spec/05_DEPLOYMENT.md:16-20`). Cloud-platform has the shapes `standard` and `poc`. Nothing in the code is called
"client install"; this note reads it as `cluster` or `cloud-platform`.

### 1.1 Model keys

| Profile | Where the key is kept | Who can read it | Picked up |
|---|---|---|---|
| local-lite, small (Compose) | The gateway's own database, `litellm`, on the deployment's Postgres, as one LiteLLM credential per engine named `osprey-<provider>` (`services/api/model_admin.py:313-314, 436-438`), sealed with `OSPREY_LITELLM_SALT_SECRET` (`harness/render.py:228-238`) | The gateway; the Conduit holds the gateway's master key (`harness/render.py:1070`) and never calls `GET /credentials` (`spec/06_DECISIONS.md:29407-29408`) | At once: `/credentials` and `/model/new` through LiteLLM's admin API; "**no service is restarted** for any change in *Models*" (`spec/06_DECISIONS.md:29372-29374`) |
| cluster | The same database; `deployment.env`'s keys are moved in at install "through the Conduit's own key path, on stdin" (`harness/cluster_install.py:316-325`) | As above | At once |
| cloud-platform | The same gateway database (on the platform's RDS). An engine declared in `osprey.yaml` may instead have its key given to Terraform as a sensitive variable in `ospreyflow-secrets` (`spec/10_ADMINISTRATION_GUIDE.md:1867-1868`; `docs/administration-guide.md:1390-1393, 1414`) | As above. The Conduit gets `ospreyflow-secrets` with each model key blank (`docs/administration-guide.md:1408`) | At once, for an engine whose way out the render made (§1.3) |
| Bedrock (cloud-platform only) | No key anywhere: "an IAM role held by the gateway's pod through its service account, so **no key is stored anywhere**" (`packages/schemas/deployment.py:305-307`); London only, `BEDROCK_REGION = "eu-west-2"` (`:311`) | The gateway pod's identity | At once; `set_key` refuses with 409 (`services/api/model_admin.py:1232-1238`) |

`deployment.env`'s `OSPREY_MODEL_KEY_<NAME>` is now only a way in at install and `apply`. Once the keys are in the
gateway, the lines are deleted and a marker is written (`harness/apply.py:173-175, 208-249`).

**No analyst-visible restart.** Today an engine or key change restarts nothing. The new form adds no restart:
- the check (§3) uses the same admin API;
- an added engine reaches Ask from the next request, as now.

### 1.2 Map keys

| Profile | Where the key is kept | Who reads it | Picked up |
|---|---|---|---|
| local-lite, small | `map-keys.yaml` in the Conduit's named volume `map-settings` at `/run/osprey/map-settings` (`services/api/map_admin.py:72-73`; `harness/render.py:1136, 1295`), mode 600, **plain text** (`services/api/map_admin.py:108, 193-198`) | The Conduit's tile proxy alone (`services/api/map_admin.py:9-11, 656-665`) | Each request: `key_for` reloads the file every call (`services/api/map_admin.py:659`); held by `test_the_map_follows_a_change_in_admin_with_no_restart` (`tests/services/api/test_map_admin_routes.py:245`) |
| cluster | A subPath of the shared ReadWriteMany volume, "shared by every Conduit replica" (`harness/cluster.py:104-105`) | As above | As above |
| cloud-platform | One ReadWriteOnce claim (`harness/cloud_platform/__init__.py:22-25`) | As above | As above |
| An `env:` reference in `osprey.yaml` | The Conduit's environment (ADR-147 decision 2a, `spec/06_DECISIONS.md:30422-30431`) | The tile proxy, after an Admin key (`services/api/app.py:9232`) | Only on a restart of the Conduit (it is read from the environment) |

After ruling 5 the file is the same, but each record is sealed (§5.2).

### 1.3 Cloud-platform: the way out is rendered, so what each form can do

**Models.**
- The render opens a host only for an engine `osprey.yaml` declares: `_engine_addresses` loops over
  `config.models.enabled_providers` (`harness/cloud_platform/__init__.py:656-669`).
- Only the gateway may use it: `engines: [litellm]` (`harness/cloud_platform/profile.yaml:73`).
- The render tells the Conduit what it made, as `OSPREY_MODEL_ROUTES_MADE` (`harness/cloud_platform/__init__.py:1208-1215`).
- Admin › Models already refuses an engine the render did not make, in these words: "On this deployment an engine is
  reached only once the render has made its way out of the namespace{identity}, and it made none for this
  engine{name}. Declare it in osprey.yaml, re-render, and have the platform team apply the Terraform; then it can be
  enabled here." (`services/api/model_admin.py:188-191, 227-237`).

Under ruling 6 the full form runs on cloud-platform. **Check the key** is refused before any call, in the same words,
when the provider's host is not made. The words name the setting: `models.providers[].name: <provider>` in
`osprey.yaml`, then the render, `helm upgrade` and Terraform (`spec/10_ADMINISTRATION_GUIDE.md:2677-2684`).

**Maps.**
- The render opens a host only for providers `osprey.yaml`'s `map:` names that are fetched through the Conduit
  (`harness/cloud_platform/__init__.py:721-728`), for the Conduit alone (`maps: [api]`,
  `harness/cloud_platform/profile.yaml:74`).
- **Admin › Maps has no equivalent of `OSPREY_MODEL_ROUTES_MADE`.** A provider added in Admin on a new host is saved.
  Its tiles then fail at the network policy, most likely as the proxy's 502 "could not be reached"
  (`services/api/app.py:9242-9252`; this last step is inferred, and no test holds it).
- Ruling 6 needs the same gate as models, `OSPREY_MAP_ROUTES_MADE`, giving the made hosts. Then **Check the key** and
  **Read the service** refuse a host not made, before any call, and name the setting: the provider in `osprey.yaml`'s
  `map.providers`, or for an organisation's service the host in `map.service_hosts` (§5.4).

## 2. The way out: which hosts a check calls, and what the form says when one does not answer

The check runs from the gateway for models and from the Conduit for maps (ruling 7; the tile proxy is in the Conduit,
`services/api/app.py:9187-9257`).

| Provider | Hosts a check calls | Source |
|---|---|---|
| Google Gemini | `generativelanguage.googleapis.com` | `harness/cloud_platform/profile.yaml:43-50`; https://aistudio.google.com/docs/api-key ("`https://generativelanguage.googleapis.com/v1beta/...`") |
| OpenAI | `api.openai.com` | `harness/cloud_platform/profile.yaml:43-50` |
| Anthropic | `api.anthropic.com` | `harness/cloud_platform/profile.yaml:43-50` |
| Azure OpenAI | `<resource>.openai.azure.com`, the address the form asks for; `management.azure.com` only to list deployments, which this design does not do (§3.1) | https://learn.microsoft.com/en-us/azure/ai-foundry/openai/reference ("`https://{your-resource-name}.openai.azure.com`") |
| Amazon Bedrock | Invoking: `bedrock-runtime.eu-west-2.amazonaws.com` (`harness/cloud_platform/profile.yaml:49-50`). Listing would add `bedrock.eu-west-2.amazonaws.com`, the control plane. STS: `sts.eu-west-2.amazonaws.com` (`profile.yaml:59, 65`) | https://docs.aws.amazon.com/general/latest/gr/bedrock.html ("bedrock.eu-west-2.amazonaws.com", "bedrock-runtime.eu-west-2.amazonaws.com"); https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_region-endpoints.html ("Europe (London) \| sts.eu-west-2.amazonaws.com") |
| Another provider or gateway | The host of the address given | `harness/cloud_platform/__init__.py:636-646` (its `api_base` host) |
| Ordnance Survey | `api.os.uk` | https://docs.os.uk/os-apis/accessing-os-apis/os-maps-api/technical-specification/wmts |
| Your organisation's service | The service's host, which must be in the installer's list (ruling 1) | ruling 1 |
| Esri ArcGIS | `basemapstyles-api.arcgis.com`, `static-map-tiles-api.arcgis.com`. A style can name further arcgis.com hosts; these are not listed here (§7) | https://developers.arcgis.com/rest/basemap-styles/; https://developers.arcgis.com/rest/static-basemap-tiles/ |
| MapTiler | `api.maptiler.com` (`api.maptiler.eu` for the EU endpoint) | https://docs.maptiler.com/_data/cloud/api/openapi.yml |
| OpenStreetMap | `tile.openstreetmap.org` | https://operations.osmfoundation.org/policies/tiles/ ("https://tile.openstreetmap.org/{z}/{x}/{y}.png") |

**What the form says when a host does not answer.** These are proposed words, one per case, never the provider's or
the gateway's own text (as Amendment 2 decision 5 already rules, `spec/06_DECISIONS.md:29425-29431`):

- **On cloud-platform, the render made no way out for this host.** This is refused before any call; the words are
  in §1.3.
- **On any profile, no answer from the host.** "Could not reach <host> from this deployment. Check that the
  deployment can reach it (a firewall or proxy may need to allow it), then check again." The engine or provider is
  not added.
- **The host answered but refused the key.** Words per status, as decision 5 does today: the key refused (401, 403),
  the model not offered (404), the provider limiting the key (429). Esri can return its token error, code 498, "Token
  Invalid", inside an HTTP 200 (community reports, not Esri's docs), so its check reads the body as well as the
  status.

## 3. Listing what a key may use

### 3.1 Models, through the gateway

The gateway can list a provider's models. LiteLLM's proxy has *model discovery*: "a wildcard entry under
`model_list`" plus "`check_provider_endpoint: true # Enable checking provider endpoint for wildcard models`".
"Discovery calls the provider with the wildcard deployment's own credentials", and `/v1/models` answers with each
model id under the wildcard's prefix. The supported providers include OpenAI, Gemini, Anthropic and Bedrock; Azure
is not listed (https://docs.litellm.ai/docs/proxy/model_discovery).

So the check runs in the gateway, under ruling 7:

1. The key is put into the gateway as a *held* credential (§5.1).
2. A wildcard route on that credential is made (`gemini/*`, `anthropic/*`, `openai/*`). It is never offered to
   analysts.
3. The Conduit asks the gateway's `/v1/models` for that route.
4. The route and the credential are removed once the engine is added, cancelled or timed out.

This depends on the pinned LiteLLM (`harness/render.py:662`, by digest) having the feature. That has not been
measured; it is the build's first live check.

| Provider | Its own list | Limited to what this key may use? | Tells the jobs apart? | Through the gateway | Typed-name fallback and its one call |
|---|---|---|---|---|---|
| Gemini | `GET /v1beta/models`, "Lists the Models available through the Gemini API." (https://aistudio.google.com/api-reference/models) | Not documented: "available through the Gemini API" only | Partly. `supportedGenerationMethods` separates chat from embedding. No image or audio flag was found in the list; image and audio input are documented per model family (https://aistudio.google.com/docs/image-understanding, https://aistudio.google.com/docs/audio) | Yes, `gemini/*` | `GET /v1beta/models/{model}` ("Gets information about a specific Model"); through the gateway, today's one-token completion |
| OpenAI | `GET /models`, "Lists the currently available models" (https://developers.openai.com/api/reference/resources/models/methods/list) | Not documented. Project allow and deny lists exist ("Use project model permissions to set an allowlist or deny list for a project", https://developers.openai.com/api/docs/guides/admin-apis.md), but no page says `/models` honours them | No: the fields are `id`, `created`, `object`, `owned_by`, `shutdown_date` | Yes, `openai/*` | `GET /models/{model}`; or the one-token completion |
| Anthropic | `GET /v1/models`, "can be used to determine which models are available for use in the API" (https://platform.claude.com/docs/en/api/models/list) | Per workspace: "A credential that belongs to a specific Workspace may omit it" (`anthropic-workspace-id`). Per key: not documented | Yes for images: "`image_input`: Whether the model accepts image content blocks." No audio exists (§3.3) | Yes, `anthropic/*` | `GET /v1/models/{model_id}`; or the one-token completion |
| Azure OpenAI | The data-plane `GET {endpoint}/openai/models` lists "base models as well as all successfully completed fine-tuned models owned by the Azure OpenAI resource", not deployments (https://learn.microsoft.com/en-us/rest/api/azureopenai/models/list). Deployments are an ARM call to `management.azure.com` (https://learn.microsoft.com/en-us/rest/api/aiservices/accountmanagement/deployments/list) | Not for deployments, which are what a call names (`azure/<your deployment name>`, https://docs.litellm.ai/docs/providers/azure/) | Flags `chat_completion`, `completion`, `embeddings`; no image or audio flag | No: discovery does not list Azure | **Typed name.** The administrator types each deployment name; the check is one one-token completion on `/openai/deployments/{name}/…` through the gateway (no documented "get one deployment" call was found) |
| Bedrock | `ListFoundationModels`, "Lists Amazon Bedrock foundation models that you can use", with `inputModalities` and `outputModalities` (https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html). Whether access is granted is a further `GetFoundationModelAvailability` per model ("`AUTHORIZED \| NOT_AUTHORIZED`") | Only with the availability call | By modality | Only with new IAM: discovery "needs the IAM permissions `bedrock:ListInferenceProfiles` and `bedrock:ListFoundationModels`" and calls "the `bedrock` control plane" (model_discovery page). Today's role grants only `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` (`harness/cloud_platform/terraform.py:913`) | **Typed name, unless the platform widens the role (§8.4).** The check is one one-token completion through the gateway, as today. Note that newer Claude models on Bedrock take on-demand calls only through an inference profile (`eu.` and similar), and today's code refuses inference-profile ids (`packages/schemas/deployment.py:579-596`). That is a separate problem, not this form's |
| Another provider or gateway | No standard. LiteLLM: "Put `openai/` in front of your model name" and "make sure your api_base has the /v1 postfix" (https://docs.litellm.ai/docs/providers/openai_compatible) | Unknown | Unknown | Try `openai/*` discovery; if `/v1/models` fails, fall back | **Typed name** and the one-token completion |

**The model prefix is the form's business.** The form adds LiteLLM's prefix (`gemini/`, `openai/`, `anthropic/`,
`azure/`, `bedrock/`) from the chosen provider. Discovered ids already carry it.

**Jobs per provider** (the form shows only the jobs a provider can do):

| Provider | Ask and extraction | Image description | Transcription |
|---|---|---|---|
| Gemini | yes | yes ("You can provide images as input to Gemini", https://aistudio.google.com/docs/image-understanding) | yes ("Transcription and translation (speech to text)", https://aistudio.google.com/docs/audio; "LiteLLM supports `gemini-3.5-transcribe` on `/v1/audio/transcriptions`", https://docs.litellm.ai/docs/providers/gemini) |
| OpenAI | yes | yes (https://developers.openai.com/api/docs/guides/images-vision) | yes, `/v1/audio/transcriptions` with `gpt-transcribe` (https://developers.openai.com/api/docs/guides/speech-to-text); its older transcription models shut down on 26 February 2027 |
| Anthropic | yes | yes (https://platform.claude.com/docs/en/build-with-claude/vision) | **no**: the Messages API's content blocks are text, image, document and others, with no audio block (https://platform.claude.com/docs/en/api/messages/create). This is an absence, not a stated "not supported" |
| Azure OpenAI | yes | yes, by deployment | yes: "`POST https://{endpoint}/openai/deployments/{deployment-id}/audio/transcriptions`" (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/reference) |
| Bedrock | yes | yes, by model (Converse's image block, https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ContentBlock.html) | **no** in Bedrock itself: Amazon Transcribe is a separate service (`transcribe.eu-west-2.amazonaws.com`, https://docs.aws.amazon.com/general/latest/gr/transcribe.html) |
| Another | all three offered; each checked by its own one call | | |

### 3.2 Maps

| Provider | Can the maps a key may use be listed? | The one call | A bad key |
|---|---|---|---|
| Ordnance Survey | Layers yes, the project's APIs no. OS Maps API: WMTS GetCapabilities with the key ("If a GetCapabilities request is being made, the other parameters are not required other than authentication", https://docs.os.uk/os-apis/accessing-os-apis/os-maps-api/technical-specification/wmts). OS Vector Tile API styles: `GET https://api.os.uk/maps/vector/v1/vts/resources/styles?srs=3857` (https://docs.os.uk/os-apis/accessing-os-apis/os-vector-tile-api/technical-specification/stylesheet.md). No API was found that lists which APIs a project holds | GetCapabilities with the key; then one tile of the chosen layer. Open and premium are split **by zoom**, not by layer: Road, Outdoor and Light in 3857 are open at zoom 7–16 and premium at 17–20 (https://docs.os.uk/os-apis/accessing-os-apis/os-maps-api/layers-and-styles). So "the premium maps" means "the premium zooms", and the check fetches one premium-zoom tile to learn whether the key's plan covers them | 401 "Unauthorized", 403 "Forbidden" (https://docs.os.uk/os-apis/core-concepts/error-codes.md); the code for a premium tile on the free plan is not documented |
| Your organisation's WMTS or WMS | Yes: GetCapabilities lists the layers. WMS 1.3.0 has per-layer `Attribution` ("Attribution indicates the provider of a Layer or collection of Layers", https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd). WMTS has no per-layer attribution; the provider and the terms come from `ows:ServiceProvider` and `ows:ServiceIdentification`'s `AccessConstraints` and `Fees` (https://schemas.opengis.net/ows/1.1.0/owsServiceIdentification.xsd) | GetCapabilities. Today's reader is WMTS only ("Scoped to WMTS only this checkpoint", `services/api/tier4_registration.py:7`) and extracts no attribution (`:69-81`), so WMS and attribution are new work | Whatever the service returns |
| Esri ArcGIS | Yes, the styles a key may use: `…/styles/v2/styles/self` ("Get a list of supported … styles and metadata", https://developers.arcgis.com/rest/basemap-styles/); static tiles `…/static-basemap-tiles-service/v1/self` (https://developers.arcgis.com/rest/static-basemap-tiles/) | `styles/self`, then one tile | 401; or code 498 in a 200 body (community reports) |
| MapTiler | No: no endpoint lists maps; every path takes a `{mapId}` (https://docs.maptiler.com/_data/cloud/api/openapi.yml) | `GET https://api.maptiler.com/maps/{mapId}/style.json?key=…`, the map id chosen from MapTiler's standard maps; see §4 before building it | 403 "Key is missing, invalid or restricted" (static maps reference; snippet; page not read) |
| OpenStreetMap | Nothing to list: no key, one map | One tile | None (no key) |

## 4. The terms: fetching through our own server, and prefetching

| Provider | Through our server | Our tile cache | Prefetching | Attribution | Sources |
|---|---|---|---|---|---|
| Ordnance Survey | **Recommended**: "The most secure approach is to keep your OS API credentials on a server that you control." | Premium data cached by end users only for 24 hours (snippet; page not read) | Not found | Open data: "Contains OS data © Crown copyright [and database right] [year]." Premium or PSGA: "© Crown copyright and database rights [year] OS [licence number]" | https://docs.os.uk/os-apis/core-concepts/authentication; https://osdatahub.os.uk/legal/apiTermsConditions (**not read: the page needs JavaScript**); https://www.ordnancesurvey.co.uk/business-government/licensing-agreements/copyright-acknowledgements |
| Your organisation's service | The organisation's own terms (`AccessConstraints`, `Fees`); none in the standard | As its terms say | As its terms say | From the capabilities where given, else typed once by the installer | OGC schemas above |
| Esri ArcGIS | Not found in any terms read | **Possibly forbidden**: "Neither Customer nor Application Users may store, cache, use, upload, distribute, or sublicense Resultant Output" (snippet; page not read) | **Forbidden**: "Systematically requesting ArcGIS tiles for offline use through other apps or services is prohibited." | "Powered by Esri" plus the data sources: "Applications that use this service must display both basemap and data attribution." | https://doc.esri.com/en/arcgis-online/latest/manage-data/take-maps-offline.html; https://www.esri.com/content/dam/esrisites/en-us/media/legal/platform/platform-legal.pdf (not read); https://developers.arcgis.com/rest/static-basemap-tiles/ |
| MapTiler | **Forbidden without MapTiler's written agreement**: "Unless otherwise agreed in writing with MapTiler, individual end-users must generate direct requests directly to MapTiler infrastructure"; "Upon request, with MapTiler's approval and additional fees incurred, the Service may be used via a Customers' proxy server." (§6.1) | **Forbidden**: "It is prohibited to store, save, and/or redistribute any map content from a server-side cache or temporary storage" (§7.2) | **Forbidden**: "it is prohibited to batch or excessive bulk download of map tiles" (§6.3) | "© MapTiler © OpenStreetMap contributors" | https://www.maptiler.com/terms/cloud/ (read 15 Nov; checked twice); https://www.maptiler.com/copyright/ |
| OpenStreetMap | **Allowed, not recommended**: "We generally do not recommend putting your own caching proxy in front of tile.openstreetmap.org." A proxy must send "a clear, unique User-Agent string that names your app" | Required: "If your cache cannot read them, cache each tile for at least 7 days." | **Forbidden**: "Bulk downloading is any pre-emptive fetching of tiles other than those a user is actively viewing." "Offline use is not permitted on tile.openstreetmap.org." | "© OpenStreetMap contributors", linking to https://www.openstreetmap.org/copyright | https://operations.osmfoundation.org/policies/tiles/ (read 15 Nov; checked twice) |

**The providers on the owner's list whose terms do not allow it:**

- **MapTiler does not allow fetching through our server** without its written agreement and extra fees. Even with
  that agreement it forbids a server-side cache and bulk download. Under ruling 2 a keyed provider whose terms forbid
  proxying "is not offered, and the form says why". This is raised in §8.1.
- **Prefetching is forbidden by MapTiler, Esri and OpenStreetMap.** Under ruling 3 each is added for live use only.
- **Esri's tile cache.** If the "Resultant Output" clause is confirmed, Esri tiles may not be kept in the
  deployment's tile cache either (`services/api/tile_cache.py:25-29`). The cache would then be off for Esri.
- **OpenStreetMap through our proxy needs a User-Agent.** The tile proxy sends none of its own today (a search of
  `services/api/tile_proxy.py` for `User-Agent` and `headers=` finds nothing). OSM "may block access, without notice,
  if your usage degrades the service", and every analyst arrives as one client. The form points to the local basemap
  for regular use, as the owner asked (`python -m scripts.build_local_basemap`, `scripts/build_local_basemap.py:476-490`;
  `ospreyflow map build <region>`, `cli/ospreyflow/maps.py:9`).
- **The direct route is needed by none of the five.** Ruling 2 allows it only for a provider that needs no key and
  whose terms require it. OSM needs no key and allows a proxy, so the form offers no direct route today.

Google Maps and Mapbox are excluded, by the owner's word, and were not researched.

## 5. Key handling, and the two amendments

### 5.1 How a model key gets from the form to the gateway, with the check first

Today's path (Amendment 2 decision 4, `spec/06_DECISIONS.md:29415-29423`) is kept, with one step added before the
engine exists:

1. The Glass field is `type="password"`, `autocomplete="off"`, never filled and cleared once sent
   (`apps/workspace/src/admin/sections/Models.tsx:249-254`).
2. The key goes to a new `POST /v1/admin/models/checks` as a `SecretStr`. The body is read by hand, so a validation
   error never echoes it, as `PUT …/key` already does (`services/api/app.py:20220`).
3. The Conduit puts it straight into the gateway as a **held credential**, `osprey-check-<random>`, with `POST
   /credentials`, as `put_credential` does today (`services/api/model_admin.py:430-440`). It then makes the
   wildcard route or the typed model on it, asks `/v1/models` or runs the one-token completion, and answers the
   form with the model ids found or a refusal in words. The Conduit keeps nothing (ruling 7).
4. **Add the engine** names that check by its id, never the key. The held credential is renamed to the engine's
   `osprey-<provider>` by delete and re-post. LiteLLM has no rename, and the Conduit never reads a credential back
   (`spec/06_DECISIONS.md:29407-29408`). So **Add** makes the engine's credential from the key a second time, and
   the form must still hold the key until **Add**. Two ways to do this:
   - **(a)** The form keeps the key in the field until **Add**, never in storage, and sends it again with **Add**.
     The key crosses the Conduit twice, in transit both times.
   - **(b)** The check makes the engine's own credential at once, and the engine row is made but kept *held*: not in
     Ask, not offered, its models not made. **Add** releases it; **Cancel** or a timeout removes it.

   **(b) is recommended.** The key crosses once, and nothing unchecked is ever offered, which is the owner's
   pattern 3. It needs the engine's held state to be shown in Admin as "Being checked" and never to analysts.
5. A held check not added within 15 minutes is removed: its credential, its route and its row. This is audited as
   "check expired".

The audit for each step names who, which provider and the outcome, never the key: "check started", "check: N models
found" or "refused: <words>", "added", "cancelled", "expired". Pattern 3's "nothing is added unchecked" is held by a
test: **Add** without a passed check is refused.

**The test the owner asked for** (rules: one per form) plants a key and proves it is absent from:

- every response, including the check's and a refusal's;
- every log record, at every level;
- every audit row;
- the models file;
- `deployment.env`.

It extends today's `test_a_planted_key_is_in_no_response_log_audit_or_maps_file`
(`tests/services/api/test_map_admin_routes.py:176-206`) and its models twin. A fake gateway must refuse what the
real one refuses (rule 15): a duplicate credential name, a route on a missing credential, and `/v1/models` with
discovery off.

### 5.2 Ruling 5: keys encrypted at rest

**Model keys.** These are already sealed by LiteLLM under `OSPREY_LITELLM_SALT_SECRET`, minted once per deployment
(`harness/render.py:228-238`), kept in `deployment.env` on Compose and in `ospreyflow-secrets` on cloud-platform
(`docs/administration-guide.md:1414`). Backups keep the sealed tables' schema but not their rows, "so every restore
brings the engines back from the models file and asks for each key again" (`harness/backup.py:392-397`).

Ruling 5 is met for the model store as built. Rotation is the gap: "a different salt silently drops every stored
engine (measured)" (`harness/render.py:233-235`). §8.3 has more.

**The map key file**, sealed:

- **The encryption key.** `OSPREY_MAP_KEYS_SECRET`: 32 random bytes, minted once at render. It ends in SECRET, so
  `keep_existing_secrets` keeps it across `apply` (`harness/apply.py:181`), as the gateway's secrets are kept.
  It goes to the Conduit alone and is blanked for every other service, as `_keys_for_the_gateway_alone` blanks model
  keys (`harness/render.py:393-417`). By profile:
  - local-lite and small: `deployment.env`.
  - cluster: the deployment's Secret.
  - cloud-platform: `ospreyflow-secrets` (Terraform's `secrets.tf`, `docs/administration-guide.md:1390`).
  - With a platform KMS (ruling 5: "or KMS"), an envelope instead: the data key sealed by a KMS key the Conduit's
    service account may use. That needs a new IAM grant and the KMS host in the egress, which is the platform
    team's work.
- **The sealing.** Each record's key is sealed with AES-256-GCM (`cryptography`, already a dependency,
  `pyproject.toml:21`). The record's provider id and address are the associated data, so a sealed key moved to
  another provider's record does not open. The record keeps a key id. `who`, `when` and `address` stay readable;
  only the key is sealed.
- **Today's plain file.** On the first start after the change, the Conduit seals every plain record in place, under
  the file's lock (`_Exclusive`, `spec/06_DECISIONS.md:30400-30404`), and audits "keys sealed: N". A test plants a
  plain file and proves that after one start no key is readable in it.
- **Rotation.** `ospreyflow secrets rotate map-keys` mints a new key and keeps the old one as
  `OSPREY_MAP_KEYS_SECRET_PREVIOUS`. The Conduit then reseals every record under the new key, one change at a time
  under the lock, and the previous key is dropped once none needs it. There is no restart beyond the one that gives
  the Conduit the new key:
  - on Compose, `apply` recreates the Conduit (seconds, the existing behaviour);
  - on cloud-platform, the platform team applies the Terraform and the pod rolls.
- **A restore.** Spec 05 §6.1 binds this: nothing in a backup may be "encrypted with a deployment-scoped key"
  (`spec/05_DEPLOYMENT.md:1167-1168`). So the sealed file stays out of every backup, as ADR-147 decision 1 already
  says ("**Never `osprey.yaml`, never a backup**", `spec/06_DECISIONS.md:30404`). A restore names each provider
  whose key must be entered again, as now. Once restored, the tile proxy says "no key: set it in Admin › Maps"
  (`services/api/tile_proxy.py:106-109`) until an administrator enters it.
- **Cloud-platform's backup looks to break this today** (§8.2).

### 5.3 Draft: ADR-135, Amendment 14 (reserved on this branch, `spec/ADR_RESERVATIONS.md`)

> ### ADR-135, Amendment 14 (<date>) — Add a model engine from the screen alone: a provider chosen from a list, its key checked in the gateway before the engine is added, its models chosen from what the gateway found or a typed name proven by one call; the guide's "never in the Admin area" brought to Amendment 2
>
> Status: accepted; the owner's prompt and rulings of 15 November 2026 (`process/lanes/admin-forms/`). It amends
> decisions 2 and 5 as Amendment 2 left them. It reverses nothing further: ruling 2's "never in the Admin area" was
> reversed by Amendment 2 on 8 November, and this amendment corrects the guide's sections that were not updated
> then. Amendment 2's rulings stand.
>
> 1. **A provider is chosen from a list**: Google Gemini, OpenAI, Anthropic, Azure OpenAI, Amazon Bedrock, and
>    "Another provider or your own gateway". Each brings its address, its LiteLLM prefix and the jobs it can do (the
>    table in `PREBUILD_FINDINGS.md` §3.1). Azure and "another" ask for the address. Bedrock shows neither key nor
>    address, says it uses the deployment's own role in London, and is offered only on cloud-platform. The label is
>    filled from the provider and can be edited. The prefix is the form's business.
> 2. **The key is checked before the engine exists, in the gateway** (the owner's ruling 7). `POST
>    /v1/admin/models/checks` takes the key once (`SecretStr`, the body read by hand). The Conduit hands it to the
>    gateway's credential store at once and keeps nothing. The engine is made **held**: shown in Admin as "Being
>    checked", never offered to analysts, its models not routable. The gateway lists the models the key may use by
>    a wildcard route with `check_provider_endpoint`, for Gemini, OpenAI, Anthropic and, where the role allows it,
>    Bedrock. Otherwise the administrator types a model name and the gateway proves it with one completion of at
>    most one token (decision 5's call). Refusals keep decision 5's fixed words. **Add** releases a held engine
>    whose check passed and is refused for one whose check did not. **Cancel**, or 15 minutes, removes the held
>    engine, its credential and its route.
> 3. **The models are chosen from what was found.** A job left alone uses this deployment's own model.
> 4. **The preview** says "Analysts will see: <label> (no contract)", or "(under contract: <reference>)", and that the
>    engine is offered only for cases whose data may leave. Agreement: the tick and `contract_reference`, as now.
> 5. **Cloud-platform**: the full form (the owner's ruling 6). A provider whose host the render did not make is
>    refused before any call, in today's words (`model_admin.py:188-191`), naming `osprey.yaml`'s `models.providers`
>    and the platform team's steps.
> 6. **Audited**: check started, its outcome, added, cancelled, expired, key replaced, key removed. Who and when,
>    never the key.
> 7. **What weakens how a key is held today.** These points are brought to the owner:
>    - The key now reaches the gateway *before* an administrator commits to the engine. A held credential lives for
>      at most 15 minutes when not added. It is in the gateway's sealed store, as every key is.
>    - A wildcard route exists for the check's length. It is never offered to analysts, and a test holds that.
>    - Nothing else changes. The Conduit's transit is Amendment 2's, already accepted. The key is never read back,
>      and the store is sealed under the deployment's salt.
> 8. **The guide.** In `10_ADMINISTRATION_GUIDE.md`:
>    - §8's `models key` row (line 2019): "writes it to `deployment.env` alone and restarts the model gateway"
>      becomes the gateway's store and "nothing is restarted".
>    - §8's key paragraph (lines 2601-2609): "never shown in the Admin area" becomes "managed in *Admin › Models*,
>      write-only: never shown back, to anyone".
>    - §10.1: gains the provider list, the check and the preview.
>    - `OspreyFlow_Core/docs/administration-guide.md` follows at lines 2228 and 2813-2821.
>
> Held by: the planted-key test across the check, add, cancel and expiry; **Add** refused without a passed check; a
> held engine absent from every analyst read; the cloud-platform refusal before any call; a fake gateway that refuses
> what LiteLLM refuses (rule 15); and the pinned LiteLLM's discovery, measured live before the list is trusted.

### 5.4 Draft: ADR-147, Amendment 5 (reserved on this branch)

> ### ADR-147, Amendment 5 (<date>) — Add a map provider from the screen alone: a provider chosen from a list, its key checked and its maps listed, an organisation's service read from its capabilities on hosts the installer allows, the ready-made profiles served, the licence confirmed and referenced, keyed providers always through the deployment, and the key file sealed at rest
>
> Status: accepted; the owner's prompt and rulings 1 to 6 of 15 November 2026. It amends decisions 1, 2 and 2a.
>
> 1. **A provider is chosen from a list**: Ordnance Survey, "Your organisation's map service (WMTS or WMS)", Esri
>    ArcGIS, and OpenStreetMap's own tile servers. MapTiler is listed or not by the owner's word on
>    `PREBUILD_FINDINGS.md` §8.1. Each brings its address, how its key is sent, its attribution, its licence and
>    whether its terms allow a cache and prefetching (§4's table).
> 2. **An organisation's service, on hosts the installer allows** (ruling 1). `osprey.yaml` gains:
>
>    ```yaml
>    map:
>      service_hosts:              # the installer's or platform team's list; Admin may add any service on these
>        - host: maps.example.gov.uk
>        - host: gis.example.gov.uk
>          port: 8443              # 443 when not given; https only
>    ```
>
>    Each entry is a host name, never an address range. On cloud-platform each is rendered into the Conduit's egress
>    allow list. **Read the service** sends GetCapabilities (WMTS, and new here, WMS 1.3.0). It lists the layers,
>    reads the attribution (WMS `Attribution`; WMTS `ows:ServiceProvider`) and reads the `AccessConstraints` and
>    `Fees`, shown to the administrator. Nothing is typed by hand. A host not in the list, or any other internal or
>    private address, stays refused under decision 2a. The form names who must add it: "Ask your installer to add
>    <host> to `map.service_hosts` in `osprey.yaml`".
> 3. **No key reaches a browser** (ruling 2). A keyed provider is always fetched by the tile proxy. A keyed provider
>    whose terms forbid proxying is not offered, and the form says why. The direct route is offered only for a
>    provider that needs no key and whose terms require it; none on the list does.
> 4. **Live use only where the terms forbid prefetching** (ruling 3): Esri, OpenStreetMap, and MapTiler if listed.
>    Prefetch areas refuse them, and the form and *Admin › Maps* say "Its terms forbid fetching tiles ahead of use, so
>    it is for live use only." Where the terms also forbid a server cache (MapTiler; Esri if confirmed), the tile
>    cache is off for that provider.
> 5. **A licence of our own** (ruling 4). Ordnance Survey's premium zooms, Esri, MapTiler and an organisation's own
>    service need a tick and the licence's reference (a contract or account number). The reference is kept with
>    the provider and shown in *Admin › Maps*. Who confirmed it, and when, is audited. The provider is not added
>    without both.
> 6. **The check.** Ordnance Survey: GetCapabilities with the key, then one tile at a premium zoom to learn whether
>    the plan covers the premium maps. Esri: `styles/self`, then one tile, reading the body for code 498. OSM: one
>    tile. An organisation's service: GetCapabilities. Refusals are in fixed words, never the provider's.
> 7. **The ready-made profiles are served** (the gap the owner named). The tile proxy resolves `profile:` through
>    `provider_profile_loader`, which no code calls today (`services/api/provider_profile_loader.py:5-8, 21`). Two
>    fixes are part of this:
>    - OS Open Zoomstack's `{api_key}` placeholder is filled (`providers/os-open-zoomstack.yaml:27`; the proxy fills
>      only `{credential}`, `services/api/tile_proxy.py:192`).
>    - The US national map's `{z}/{y}/{x}` template, though `service: wmts`, is fetched as a template
>      (`providers/usgs-national-map.yaml:18-19`; `packages/schemas/mapconfig.py:157-162`).
>
>    The screen's refusal of a profile (`services/api/map_admin.py:503, 680`) goes.
> 8. **The key file is sealed at rest** (ruling 5), as `PREBUILD_FINDINGS.md` §5.2 says: the key, the per-record
>    sealing, the reseal of today's plain file, rotation, and a restore that asks again. The file stays out of every
>    backup (spec 05 §6.1).
> 9. **Cloud-platform: the full form, gated by the platform** (ruling 6). The render gives the Conduit
>    `OSPREY_MAP_ROUTES_MADE`, as models have `OSPREY_MODEL_ROUTES_MADE`. A check or read on a host not made is
>    refused before any call, naming `map.providers` or `map.service_hosts`.
> 10. **OpenStreetMap through the proxy** sends a User-Agent that names the deployment's product and the
>     administrator's contact, as OSM's policy requires, and honours OSM's caching headers or seven days. The form
>     says its servers are for light use and points to the local basemap.
>
> Held by: the planted-key test (the key in no response, log line, audit row, maps file or backup), the sealed file
> unreadable without the deployment's key, a reseal of a plain file, a profile tile served, live-only providers
> refused by prefetch, a licence refused without its reference, a host outside `service_hosts` refused, and the
> cloud-platform refusal before any call.

## 6. Estimates and lanes

These are working days for one lane, red-first tests included, with both looks, every theme and the accessibility
checks:

| Part | What | Estimate | Lane |
|---|---|---|---|
| M1 | Admin › Models form: provider list, label, address, jobs, models found, preview, held state, both looks, `keyboard.spec.ts` steps (rule 13) | 2 d | admin |
| M2 | Conduit and gateway: held checks (§5.1), discovery by wildcard route, the typed-name call, the provider catalogue, expiry, audit; the planted-key test; a live measurement of the pinned LiteLLM's discovery under a lease | 3 d | admin |
| M3 | Bedrock listing, if the owner widens the role (§8.4): IAM, the control-plane host in the render, Terraform | 1 d | platform-b |
| M4 | ADR-135 Am 14 written, the guide's corrections (both copies) | 0.5 d | admin |
| P1 | Admin › Maps form, the same pattern | 2 d | admin |
| P2 | Conduit: provider catalogue, the checks per provider, OS premium-zoom check, WMS and attribution reading, `service_hosts`, licence reference, live-only, cache off per provider, OSM User-Agent | 3.5 d | admin |
| P3 | Profiles served by the tile proxy (the two template fixes) | 1 d | admin |
| P4 | Key file sealed: mint, seal, reseal of the plain file, rotate verb, restore words; cloud-platform's backup exclusion (§8.2) | 1.5 d | platform (render, backup), admin (Conduit) |
| P5 | Cloud-platform: `OSPREY_MAP_ROUTES_MADE`, `service_hosts` into the egress | 1 d | platform-b |
| P6 | ADR-147 Am 5 written, the guide | 0.5 d | admin |

**Total about 16 days.** The owner said one lane may build both forms. admin holds the Admin sections and their
rights (People and roles, ADR-148 Amendments 15-19; Admin's type scale, ADR-145 Amendment 16), so it builds M1, M2,
M4 and P1 to P3 and P6, in about 12.5 days. The render, backup and Terraform parts, M3, P4's render and backup half
and P5, go to platform or platform-b in about 3.5 days, in parallel once the shapes in §5 are agreed.

## 7. What was not read, and must be before the list ships

- **Ordnance Survey's API Service Terms**, https://osdatahub.os.uk/legal/apiTermsConditions. The page needs
  JavaScript; only search snippets were seen, among them the 24-hour limit on caching premium data. A person needs
  to read it in a browser for caching and prefetching rules.
- **Esri's ArcGIS Location Platform Agreement and Product-Specific Terms (E300)**. These are PDFs that could not be
  read here. The "Resultant Output" caching clause and a clause on exporting volumes of tiles are snippets only.
- **The arcgis.com hosts a style names**, for the egress list.
- **The OpenAI and Gemini lists are not documented as limited to a key's allow list.** A list may name a model the
  key cannot use, so the form runs the one-token call on each chosen model before **Add** in any case.
- **Whether the pinned LiteLLM has model discovery.** The image is pinned by digest (`harness/render.py:662`); its
  version and this feature need a live check under a lease.

## 8. Raised with the orchestrator: impossible or unsafe as ruled, not designed around

1. **MapTiler and ruling 2.** MapTiler is keyed, and its terms require "individual end-users [to] generate direct
   requests directly to MapTiler infrastructure" unless agreed in writing (§6.1). They also forbid any server-side
   cache (§7.2) and bulk download (§6.3). By ruling 2 it "is not offered". The owner chooses one of two:
   - drop it from the list;
   - offer it only where the administrator ticks a written proxy agreement with MapTiler and gives its reference
     (ruling 4's tick), with the tile cache off and live use only.

   Its direct route would put the key in every analyst's tile URL, which ruling 2 forbids.
2. **Today's cloud-platform backup appears to copy the plain map key file.** The cloud runbook says the deployment's
   backup covers "map settings with the map key file (`map-settings`)" (`deploy/RUNBOOK.md:163-164`). The backup's
   parts include `{"name": "shared-map-settings", "subPath": "map-settings"}`
   (`harness/cloud_platform_backups.py:340`), and no exclusion of `map-keys.yaml` was found in that module. That
   would break ADR-147 decision 1 ("never a backup", `spec/06_DECISIONS.md:30404`) and spec 05 §6.1 today, with the
   key in plain text. This is unverified against a running backup. platform-b should confirm it; if confirmed, it is
   a fix now, not after the cut.
3. **Rotating the model store's key.** Ruling 5 asks how the key is rotated. LiteLLM seals credentials with the salt,
   and "a different salt silently drops every stored engine (measured)" (`harness/render.py:233-235`). So rotating
   the model store's key, as pinned, means re-entering every engine's key; nothing seals them again in place.
   A reseal through LiteLLM would need its own measured procedure. The draft says so rather than promise rotation.
4. **Bedrock listing needs a wider role.** Listing needs `bedrock:ListFoundationModels` and
   `bedrock:ListInferenceProfiles`, and the `bedrock` control-plane host. Today's role grants only `InvokeModel` and
   `InvokeModelWithResponseStream` (`harness/cloud_platform/terraform.py:913`). Widening it reveals no data, but it is
   a change to the gateway's grant for the owner to approve. Without it, Bedrock is a typed name checked by one call.
5. **Ordnance Survey's and Esri's terms** are not read in full (§7). Esri's possible ban on caching would turn the
   tile cache off for Esri. OS's 24-hour premium limit would cap that provider's cache time. Neither should ship on a
   snippet.

## 9. Point 5 closed: Esri's and Ordnance Survey's terms read in full (the orchestrator, 15 November 2026)

**Esri**, ArcGIS Location Platform agreement E204 ("Platform Legal", dated 21 November 2025, 11 pages), downloaded from
https://www.esri.com/content/dam/esrisites/en-us/media/legal/platform/platform-legal.pdf and read whole.
- §3.1(d)(6): "Neither Customer nor Application Users may scrape, download, or extract Resultant Output, nor cache or
  store Resultant Output except as outlined herein: A. Customer may allow pre-caching of Resultant Output as permitted
  by the caching headers (HTTP/1.1 standard or future standard) returned by Location Services to the extent necessary
  for enabling or optimizing the use of the Customer Application". So **no prefetch areas**: Esri is live-only under
  ruling 3, and any cache follows Esri's own caching headers.
- §3.1(d)(2): "A single request for Resultant Output may not be used to serve multiple users." So the tile proxy may
  fetch Esri for an analyst, but **must not serve one cached Esri tile to a second analyst**: no shared cache for Esri.
- §3.1(d)(4): an attribution statement acknowledging Esri and its licensors on the Basemap service's output.

**Ordnance Survey**, OS Data Hub API Terms (https://osdatahub.os.uk/support/legal/api-terms, rendered in a browser,
80,554 characters, read 15 Nov 2026):
- "You can allow your Premium API Service End Users to … temporarily cache it for up to 24 hours". So a premium tile's
  cache is **at most 24 hours**.
- "You must not permit or enable your End Users to download, store or extract Premium API Data except to the extent
  expressly provided for". So **premium maps are live-only** (ruling 3).
- "You can allow your Premium API Service End Users to do anything with Open API Data in accordance with the Open
  Government Licence." So **OS Open Zoomstack may be prefetched**.
- **An obligation for premium data:** "You shall at all times maintain a list (including organisation names and contact
  details) of all End Users with access to Premium API Data … and shall make that list available to us on our request",
  and the End User Licence must pass on OS's terms and let OS enforce them. The licence tick for OS premium (ruling 4)
  should say so in words.
- "the acknowledgement of OS and Crown copyright and database rights ownership is in a conspicuous position".
