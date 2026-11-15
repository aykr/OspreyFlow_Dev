# Admin: add a model engine or a map provider from the screen alone

From the owner, 15 November 2026. **After the cut. Nothing here joins v0.5.2 or delays steps 6 and 7.** Start it when a lane is free after the cut. The two forms share one pattern, so one lane may build both. Either may go onto the demo from main when it is ready, on my word.

## Why

I tried to add Gemini on the demo. The form asked me to type the provider's name, to type a model name with a prefix I had to look up, left the address blank, and sent me to a command on the server for the key. A wrong model name is accepted and only fails when someone asks a question. Adding a map provider is the same kind of work: an address, a layer and settings typed by hand.

An administrator should be able to add either from the screen alone, and know it works before leaving it.

## The pattern, for both forms

1. **Choose a provider from a list.** The form then knows that provider: its address, what it offers, and what it needs.
2. **Give the key in the form**, where the provider has one.
3. **Check before adding.** One button proves the key and lists what it may use. Nothing is added unchecked, and a refusal is said in words.
4. **Choose from what was found**, not from memory.
5. **See what analysts will see** before adding.

Clickable sketches, in a neutral style, are in `Claude outputs/ospreyflow_admin_forms_2026-11-15/` (git-ignored, at the repository root): `model_form_simulation.html` and `map_form_simulation.html`. They show behaviour and wording only. Their checks are pretend, and their model names, map names and licence words are examples. Use each look's own components.

## Part 1. Admin › Models

| Part | Today | Change to |
|---|---|---|
| Provider | A name typed in | A list: Google Gemini, OpenAI, Anthropic, Azure OpenAI, Amazon Bedrock, and "Another provider or your own gateway" |
| Label | Empty | Filled from the provider, editable |
| Address | Blank, meaning the provider's own | The provider's own address shown, with "Change" for a gateway. Azure and "another provider" ask for it. Bedrock shows none |
| Jobs | Three rows for every provider | Only the jobs that provider can do |
| Model | A name typed in, with its prefix | Chosen from the models this key can use, asked of the provider. The prefix is the form's business. A job left alone uses this deployment's own model |
| Key | A command on the server | A field in the form, under the key rules below |
| Preview | None | "Analysts will see: Gemini (no contract)", and that it is offered only for cases whose data may leave |
| Agreement | A tick | The tick, and when ticked the agreement's reference, as today's `contract_reference` |

Bedrock keeps what it has today: no key and no address, the deployment's own role, London only. The form says so.

## Part 2. Admin › Maps

*Admin › Maps* already takes a provider's key, write-only. What it lacks is a form that knows the provider. Two ready-made providers ship in `providers/` (OS Open Zoomstack and a US national map), but the screen refuses a ready-made provider and the tile proxy does not serve one yet. That gap is part of this work.

| Part | Change to |
|---|---|
| Provider | A list: Ordnance Survey, "Your organisation's map service (WMTS or WMS)", Esri ArcGIS, MapTiler, and OpenStreetMap's own tile servers |
| Ordnance Survey | One key from the OS Data Hub. The maps it may use are listed: OS Open Zoomstack as open data, and the premium maps |
| Your organisation's map service | An address and "Read the service", which lists its layers and reads its attribution, as tier-4 registration does today. Nothing typed by hand |
| OpenStreetMap | No key. The form says its own servers are for light use and points to the local basemap for regular use |
| Map | Chosen from what the check found |
| Name analysts see | Filled from the map, editable |
| How the tiles are fetched | Through this deployment, always, so analysts' browsers never contact the provider and the key stays on the server. The direct route is offered only where a provider's terms or design need it |
| Licence and attribution | Shown before adding: the attribution that will appear on the map, and the licence. Where a licence of our own is needed (Ordnance Survey's premium maps, Esri, MapTiler, an organisation's own service), a tick confirms we hold it, and the provider is not added without it |
| Default | "Make this the default basemap" |
| Preview | What appears in the map's Basemap switch |

Before building the list, check each provider's terms for fetching through our own server and for prefetching, and tell me if any provider on my list does not allow it. Do not add Google Maps or Mapbox without asking me.

## The key: my rules, for both forms

1. **Write-only.** The key is sent once and never shown again, to anyone. The form says only "key set" or "no key".
2. **Replace and remove, never reveal.**
3. **Audited.** Who set, replaced or removed a key, and when. Never the key, and never in a log, an error, a URL or the browser's storage.
4. **Only a holder of the right for that section** (models, or `manage_geospatial`).
5. **The server commands stay** (`ospreyflow models key`, and the map commands), as a second route. Both routes end in the same place.
6. A model key is still read only by the model gateway. Say how it gets from the form to the gateway without the Conduit keeping it, and follow what *Admin › Maps* already does where that fits.

For models this changes a decision: the guide says a model key is never given in the Admin area. Write the ADR amendment, and bring me anything in it that weakens how a key is held today.

## What I need to know before you build

1. **Each profile.** On the standard shapes, where each key is kept and how it is picked up without a restart an analyst would notice. On cloud-platform, where a provider's way out is rendered from `osprey.yaml`: what each form can do there, and what it says when the platform team must act first.
2. **The way out.** Checking a key calls the provider. Which hosts must be reachable, and what the form says when one is not.
3. **Listing.** Whether each model provider can list the models a key may use through the gateway, and each map provider the maps a key may use. Where one cannot, the form falls back to a typed name, checked with one small call before anything is added.
4. **The terms**, as asked in Part 2.
5. **Estimate** for each part, and the lane.

## Rules

- Both looks, every theme, and the accessibility checks: every field labelled, errors tied to their fields, a key field never auto-completed.
- Tests red first, including one for each form proving the key appears in no response, log line or audit row.
- The administration guide follows, including its section that says a model key is never given in the Admin area.
- Protected files come to me as diffs.

Do not defer or drop anything without asking.
