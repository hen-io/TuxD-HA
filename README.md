# TuxD Home Assistant Integration

Lets [TuxD](https://github.com/hen-io/tuxd) agents connect **directly** to Home Assistant over an
encrypted, authenticated WebSocket instead of through an MQTT broker. Install this alongside TuxD
if you want `connection_mode: direct` in `tuxd.conf` - MQTT remains fully supported and is still
the default; this is an additive option, not a replacement.

## Install

1. Add this repository to HACS (category: Integration), or copy `custom_components/tuxd/` into
   your Home Assistant `config/custom_components/` folder manually.
2. Restart Home Assistant.
3. **Settings -> Devices & services -> Add integration -> TuxD.**
4. Copy the pairing key shown - it's shown once. Paste it into every agent's `tuxd.conf`:

   ```yaml
   tuxd:
     connection_mode: "direct"

   home-assistant:
     url: "https://your-ha-instance:8123"
     verify_ssl: true
     api_key: "<the pairing key>"
   ```
5. Restart the agent. Its device and every entity it publishes appear in Home Assistant
   automatically, the same way they would over MQTT discovery - no per-device setup step.

Only one TuxD integration entry is ever needed - every agent shares the same connection endpoint.
Lost the pairing key? Use the integration's **Reconfigure** option to generate a new one (every
agent's `tuxd.conf` will need updating to match).

## Why this exists

MQTT is still the simplest, most broadly-compatible option and stays the default. Direct mode is
for anyone who'd rather not run/expose a broker at all: agents dial straight out to Home Assistant
over the same HTTPS port it already uses, authenticated with a pre-shared pairing key, no broker,
no separate port, no certificate management beyond whatever TLS Home Assistant itself already has.
