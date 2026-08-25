# Tuya Watering

Weather-aware watering valve control for Home Assistant via Tuya/Zigbee.

Supports local LAN control (fast, no cloud latency) with automatic Tuya Cloud
fallback. Any number of valves. Ships with automation blueprints for
weather-based and manual watering.

## Prerequisites

- **[Tuya Home Core](https://github.com/a000a999a/ha-tuya-home-core)** installed and configured
- Tuya-compatible Zigbee water timer (default: GIEX GX-02BT)
- Gateway local IP, local key, gateway ID, and each valve's device_id/sub_cid
  — see **Finding these values** below
- `tinytuya` — installed automatically by Home Assistant from this
  integration's manifest (no manual `pip install`). Used only at runtime to
  send local LAN commands to the valve; not involved in either discovery
  method below.

### Finding these values

Two independent discovery methods for device_id/sub_cid — pick either one:

1. **Recommended, no Tuya Developer Platform account needed:** this
   integration's own Add/Edit Valve → Import picker, backed by the
   `tuya_sharing` SDK (the same one the official Tuya integration uses). See
   [docs/device_discovery.md](docs/device_discovery.md) for how it works and
   why it doesn't need `tinytuya` or an IoT Core subscription.
2. **Alternative:** the [tinytuya wizard](https://github.com/jasonacox/tinytuya)
   — a separate CLI discovery tool from the `tinytuya` project. Requires its
   own Tuya Developer Platform project (Access ID/Secret) and an active IoT
   Core subscription; unrelated to the `tinytuya` Python package this
   integration installs automatically for runtime control.

Neither method discovers the **gateway's** IP/local key/ID — those aren't
exposed by either the `tuya_sharing` SDK or the Cloud API for this device
type, so enter them manually once (see docs/device_discovery.md for why this
is fine in practice).

## Installation via HACS

1. Install **Tuya Home Core** first
2. In HACS → Custom repositories, add `a000a999a/ha-tuya-watering`
3. Install **Tuya Watering** and restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration → Tuya Watering**

## Configuration

### Step 1 — Select Tuya account
Choose your Tuya Home Core entry (auto-selected if only one exists).

### Step 2 — Add first valve

| Field | Required | Description |
|---|---|---|
| Valve name | Yes | Display name (e.g. "Terrasse") |
| Tuya Device ID | Yes | Sub-device ID from Tuya platform |
| Gateway ID | No | Local gateway device ID |
| Gateway IP | No | Local gateway IP address |
| Gateway local key | No | Local key (from tinytuya wizard) |
| Sub-device CID | No | Sub-device CID (from tinytuya wizard) |
| Default duration | No | Seconds to run (default: 120) |
| DPS duration code | No | DPS for duration — GIEX default: **104** |
| DPS trigger code | No | DPS to start — GIEX default: **116** |
| DPS stop code | No | DPS to stop — GIEX default: **1** |

> **Cloud-only mode**: leave all gateway fields blank. Valve opens via Tuya Cloud (~1-2s delay).
> **Local mode**: fill gateway fields. Valve opens via LAN (<0.5s), falls back to cloud on failure.

### Adding more valves
Go to **Settings → Devices & Services → Tuya Watering → Configure → Add a valve**.

## Automation Blueprints

Import from **Settings → Automations → Blueprints → Import Blueprint**.

| Blueprint | URL |
|---|---|
| Weather-Based Watering | `https://github.com/a000a999a/ha-tuya-watering/blob/main/blueprints/automation/tuya_watering/weather_based_watering.yaml` |
| Manual Watering Trigger | `https://github.com/a000a999a/ha-tuya-watering/blob/main/blueprints/automation/tuya_watering/manual_watering.yaml` |

### Weather-Based Watering blueprint inputs

| Input | Default | Description |
|---|---|---|
| Weather entity | — | Any HA weather entity |
| Valve(s) | — | Your Tuya Watering switches |
| Start time | — | Daily trigger time |
| Duration | 2 min | How long to water |
| Rain threshold | 40% | Skip if rain probability ≥ this |
| Storm conditions | rainy, pouring, hail… | Skip if today's condition matches |

## Dashboard

No manual dashboard setup needed — the integration creates and keeps two
cards on your Overview dashboard's Home view in sync automatically:

- **Tuya Watering** — a toggle for every configured valve
- **Tuya Watering Schedule** — any automation, duration, or start-time helper
  entity it can find that belongs to one of your valves (see naming below).
  Only appears once at least one valve has something to show.

This runs automatically whenever a valve is added, edited, or removed — and
on every Home Assistant restart. It's purely additive: it only ever touches
these two cards by title, never anything else you've added to that view. You
can also trigger it manually with the `tuya_watering.refresh_dashboard`
service (e.g. right after importing a blueprint automation, instead of
waiting for the next reload).

**For the Schedule card to find your automations/helpers:** name them so the
entity_id contains your valve's name as a whole word — e.g. a valve named
"Terrasse" (`switch.terrasse`) is matched by `automation.watering_terrasse_run_1`,
`input_number.watering_terrasse_run1_duration`, `input_datetime.watering_terrasse_run1_time`,
etc. (HA derives the entity_id from whatever name you give the automation/helper,
so just make sure the valve's name appears in it.) This is exactly what you get by
naming things consistently when importing the blueprints above or defining
helpers by hand — no special setup required beyond that.

## DPS codes for common valves

| Device | Duration DPS | Trigger DPS | Stop DPS |
|---|---|---|---|
| GIEX GX-02BT (default) | 104 | 116 | 1 |
| Most generic Tuya timers | 2 (countdown) | 1 (switch) | 1 |

> If your valve uses different codes, set them in the integration configuration.
> Open an issue with your device model to help build this table.

## Entities created

Each configured valve creates:
- `switch.<valve_name>` — open/close control (optimistic state)

## Services

| Service | Description |
|---|---|
| `tuya_watering.open_valve` | Open valve, optional `duration` (seconds) |
| `tuya_watering.close_valve` | Close valve immediately |
| `tuya_watering.refresh_dashboard` | Force an immediate dashboard card refresh (see [Dashboard](#dashboard)) |
