# Tuya Watering

Weather-aware watering valve control for Home Assistant via Tuya/Zigbee.

Supports local LAN control (fast, no cloud latency) with automatic Tuya Cloud
fallback. Any number of valves. Ships with automation blueprints for
weather-based and manual watering.

## Prerequisites

- **[Tuya Home Core](https://github.com/a000a999a/ha-tuya-home-core)** installed and configured
- Tuya-compatible Zigbee water timer (default: GIEX GX-02BT)
- For local control: gateway local IP, local key, gateway ID, sub-device CID
  (use the [tinytuya wizard](https://github.com/jasonacox/tinytuya) to discover these
  — or, if your Tuya Developer Platform subscription has expired, the built-in
  Import picker in this integration's Add/Edit Valve flow gets you device_id/sub_cid
  without it; see [docs/device_discovery.md](docs/device_discovery.md))

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
