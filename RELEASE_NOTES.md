## What's Changed in v2.0.0-rc1 (Release Candidate)

This is a **release candidate** for beta testing through HACS's beta channel
against a real controller, ahead of the stable v2.0.0 release. It builds on
v1.10.1.

### Added

- **New client action services**, scoped to a config entry so they also
  reach clients that were never selected for entity creation:
  - `omada_open_api.block_client` / `omada_open_api.unblock_client`
  - `omada_open_api.set_client_rate_limit` / `omada_open_api.clear_client_rate_limit`
  - `omada_open_api.get_client_snapshot` — returns every client for a site
    keyed by MAC with exact byte counters, useful for spotting
    unknown/unselected clients.
  - `site_id` is optional on all of these and defaults to the entry's only
    site, with a translated validation error if the entry monitors more than
    one site.
- Client records now expose a `rate_limited` attribute (mirroring the
  existing `blocked` attribute), reflecting whether a rate limit is
  currently enforced on that client.

### Install for beta testing

In HACS, enable **Show beta versions** for this repository, then select
`2.0.0rc1` in the "Redownload" dialog.

---

**Feedback:** please report any issues found while testing this release
candidate before it is promoted to a stable v2.0.0 release.
