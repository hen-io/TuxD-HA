# TuxD brand assets

Home Assistant doesn't read integration icons from `custom_components/` itself -
every icon shown in Settings > Devices & Services, the integrations list, and
each device's own page comes from the community-maintained
[home-assistant/brands](https://github.com/home-assistant/brands) repository.
Until TuxD has an entry there, HA just shows a generic puzzle-piece icon.

## What's here

Generated from `MASTER/bin/logo.png` (the existing TuxD mascot), resized to
the exact files/sizes `home-assistant/brands` expects for a custom
integration:

- `icon.png` - 256x256
- `icon@2x.png` - 512x512
- `logo.png` - 256x256 (same art - TuxD doesn't have a separate wide
  wordmark-only logotype; reusing the icon is normal for a simple brand)
- `logo@2x.png` - 512x512

These are ready to submit as-is, or swap in something more polished first -
the mascot art works, but a HACS/HA reviewer respond faster to a clean,
purpose-made icon rather than a resized app-icon-style asset with a drop
shadow and rounded corners already baked in (brands.home-assistant.io
frontend applies its own rounding/framing, so a source image that already has
a rounded square baked in can look doubled-up in context).

## To actually get it live in HA

1. Fork `home-assistant/brands` on GitHub.
2. Add a `custom_integrations/tuxd/` folder there with these same four files.
3. Open a PR. Their CI checks exact pixel dimensions and file format - keep
   these sizes.
4. Once merged (their maintainers review these fairly regularly), HA and
   HACS both start showing it automatically - no code change needed on the
   TuxD side, no version bump, nothing to release. It just starts resolving.

This is a public PR to a project you don't control, so it's left for you to
open when you're ready rather than done automatically.

## Optional: dark-mode variants

`home-assistant/brands` also accepts `dark_icon.png`, `dark_icon@2x.png`,
`dark_logo.png`, `dark_logo@2x.png` for a variant shown when HA's frontend is
in dark mode. Worth doing only if the current art doesn't already read well
on a dark background (the blue gradient background here mostly does - a
transparent-background version would look better still, but is a bigger
redo of the source art, not a resize).
