# Finding device_id / sub_cid without a Tuya IoT Core subscription

Local control needs three things per valve: the shared **gateway** local key/IP/ID,
and each valve's own **device_id** + **sub_cid** (Zigbee node id). The
[tinytuya wizard](https://github.com/jasonacox/tinytuya) referenced in the main
README is one way to get these — but it authenticates against the Tuya
**Developer Platform** (IoT Core), which requires an active subscription. Trial
Edition subscriptions expire and block every device-list/detail endpoint with
`Error 28841002: IoT Core service subscription has expired` — including the
Cloud API step in tools like LocalTuya's setup wizard.

You don't need IoT Core for this. `sub_cid` in particular is a Zigbee-local
concept that Tuya's Cloud device-list API can never expose anyway, subscription
or not — the working method here bypasses the Developer Platform entirely.

## How this integration does it

**Tuya Home Core** (this integration's dependency) authenticates via the
official Home Assistant **Tuya** integration — a Smart Life account login, not
a Developer Platform project. That login creates a live `tuya_sharing.Manager`
session which polls the **SmartLife consumer endpoint**
(`/v1.0/m/life/users/homes`), not the quota-limited Developer API. This session
already lists every device on the account, including each Zigbee sub-device's
`node_id` (what this project calls `sub_cid`).

When you open **Add Valve** or **Edit Valve**, the config flow calls
[`tuya_discovery.py::discover_valve_candidates()`](../custom_components/tuya_watering/tuya_discovery.py),
which:

1. Walks the official Tuya hub's `device_map` (via
   `entry.runtime_data.manager.device_map`)
2. Filters for `category == "sfkzq"` — the category code GIEX-style Zigbee
   water timers report (broaden this constant in the source if your valve
   model uses a different category)
3. Reads `.id` (device_id) and `.node_id` (sub_cid) off each match
4. Offers matches in a picker — pick one and both fields are filled in for you

No Developer Platform account, Access ID/Secret, or IoT Core subscription is
involved anywhere in this path. If nothing shows up in the picker, the flow
falls back to the manual entry form unchanged — this discovery step is
best-effort by design (see the function's docstring) and never blocks setup.

**Gateway fields are the exception** — IP, local key, and gateway device ID
are *not* discoverable this way. Validated live: Zigbee gateway devices don't
expose `local_key` through the `tuya_sharing` SDK path, only their valve/sensor
sub-devices do. This isn't a problem in practice: sub-devices don't carry their
own separate key, they're addressed *through* the gateway's shared key
(`tinytuya.Device(cid=sub_cid, parent=gateway)`), so the gateway's fields only
need entering once and rarely change.

## Using this to configure a different integration (e.g. LocalTuya)

LocalTuya's own setup wizard has a Cloud API discovery step, but it's gated by
the same expired-subscription problem, and it has no `tuya_sharing` fallback
built in. If you're setting up LocalTuya (or anything else that wants a raw
`device_id`/`sub_cid` pair) instead of this integration:

1. Add the device as a **Tuya Watering** valve entry purely to trigger the
   Import picker described above
2. Note the `device_id` and `sub_cid` it shows you
3. Delete that entry (or leave it — it's harmless either way)
4. Paste the same two values into the other integration's manual/local entry
   form, along with the gateway's IP/local key/ID (entered once, unchanged)

## Prerequisite

This all depends on **Tuya Home Core** being configured with a linked official
Tuya hub (Settings → Devices & Services → Tuya Home Core → Configure → "Linked
Tuya hub") — the picker returns nothing if that link isn't set, and Home Core
falls back to unscoped discovery instead. See `ha-tuya-home-core`'s README for
the linking step.
