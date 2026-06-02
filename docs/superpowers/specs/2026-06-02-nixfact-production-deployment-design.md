# NixFact Production Deployment — Design

> Date: 2026-06-02
> Owner: Nick Aldewereld — Aldewereld Consultancy
> Status: Approved design, pending implementation plan
> Sub-project: **A** of four (see "Scope & decomposition")

## Summary

Stand up a reliable, self-hosted production instance of ERPNext + the
`nixfact_integration` app on the home Proxmox host `pro` (Dell R220), reachable
at `https://erp.aldewereldconsultancy.nl` through the existing Hostinger VPS
front door (Caddy + Authentik over a Tailscale subnet route). This delivers the
**production foundation** the rest of the work builds on. It is explicitly *not*
yet a full WeFact replacement.

## Scope & decomposition

The broader goal ("second brain for all ventures; replace WeFact") is four
independent sub-projects, each with its own spec → plan → implementation:

- **A — Production deployment (this spec).** A reliable hosted ERPNext+NixFact
  instance with backups, TLS, and SSO.
- **B — WeFact gap analysis.** What NixFact must do to actually replace WeFact,
  including the CRM features now under WeFact Plus (tasks, interactions,
  quotation follow-up, mailings).
- **C — Multi-venture data model.** How to structure all ventures/companies in
  one ERPNext (native multi-company).
- **D — WeFact → NixFact migration.** Moving customers, invoices,
  subscriptions, settings; run parallel, then cut over.

**Non-goals for A:** feature parity with WeFact, data migration, multi-company
modeling. The WeFact CRM beta expiry (30 days) is not a hard deadline — invoices,
customers, and settings persist in WeFact regardless; only the CRM beta data
lapses. This gives room to do A→D properly rather than rushing a migration.

## Environment (as discovered on host `pro`)

- Proxmox VE 9.2.2; Dell R220, Xeon E3-1271 v3 (4c/8t), 32 GB RAM (~9 GB free at
  rest, 8 GB swap), 15 existing guests.
- Storage: `local-lvm` (SSD lvm-thin, ~689 GB free) for OS/root disks;
  `/mnt/pve/wd1tb` (HDD, ~600 GB free) for bulk/backups; `local-pbs` (Proxmox
  Backup Server) available.
- Networking: `pro` is a Tailscale subnet router advertising `192.168.178.0/24`.
  Public ingress pattern is established: Internet → **Caddy on the VPS**
  (88.222.220.64, :443) → Tailscale subnet route → the guest's LAN IP. No ports
  open on the Ziggo modem. Examples already live: `foto.` (immich, LXC 210),
  `sign.` (docuseal, LXC 212).
- Docker-in-LXC is routine here (immich, docuseal, greenbone, pentestswarm) via
  `lxc-factory.sh ... --with-docker` (sets `nesting=1`, `keyctl=1`).
- `pro`'s own note records that VMs with `firewall=1` caused double-MASQUERADE
  problems over the Tailscale subnet route, while **LXCs do not** — so LXC is the
  better substrate for this ingress pattern, not just a preference.
- Conventions: code/config/docs in **English**, owner comms in **Dutch**; LXCs
  numbered `.200+` (next IP via `pro-toolkit.sh lxc next-ip`); secrets in
  `/root/.secrets/*.env` on `pro`; all containers unprivileged; SSD for root
  disks, HDD for bulk/backups; `pve-no-subscription` repo.

## Decisions

| Topic | Decision |
|-------|----------|
| Access model | Public via `erp.aldewereldconsultancy.nl` (A record already → VPS), behind the VPS front door. |
| Tunnel | Existing **Headscale/Tailscale** subnet route (already active); no per-host enrollment needed. |
| Substrate | Single **unprivileged LXC** on `pro`, created with `lxc-factory` `--with-docker`. |
| Stack form | **Docker-compose** (`deployment/docker/docker-compose.yml`), RAM-trimmed. |
| Auth | **Authentik OIDC SSO** into Frappe (single login). Consistent with the Nextcloud installs already using Authentik OIDC on the VPS. |
| Reverse proxy / TLS | **Caddy on the VPS** (automatic Let's Encrypt), same pattern as `sign.`/`foto.`. |
| Backups | Layer 1: nightly `bench backup` → HDD bind-mount picked up by existing borgmatic (LXC 200). Layer 2 (optional): weekly PVE `vzdump` → `local-pbs`. |

## Architecture

```
Internet → erp.aldewereldconsultancy.nl (A → 88.222.220.64)
   │
   ▼  Caddy on VPS (TLS, security headers)  ── Authentik (OIDC provider)
   │  reverse_proxy over Tailscale subnet route (192.168.178.0/24)
   ▼
pro (R220) → LXC "nixfact" (192.168.178.X, unprivileged, --with-docker)
   └─ docker compose: mariadb · redis-cache · redis-queue · web · worker · scheduler
        web bound on the LXC LAN IP so Caddy can reach it over the subnet route
```

### Components (in the LXC)

Reuse `deployment/docker/docker-compose.yml` as-is in structure, trimmed:

- **mariadb** (10.11) — data on the SSD root disk. `~1g` limit.
- **redis-cache**, **redis-queue** (7-alpine) — `~192m` each.
- **web** (the built `nixfact` image) — Frappe/gunicorn + nginx. `~1.5g` limit.
  Port bound to the LXC LAN IP (not only `127.0.0.1`) so Caddy reaches it.
- **worker** — short and long queues merged into one worker to save RAM. `~768m`.
- **scheduler** — `~256m`.

Trimmed ceilings sum to ~3.9 GB, under the 4 GB LXC cap; tune against real usage
after go-live. The data plane stays on the `internal: true` backend network (no
outbound internet), per the compose file's existing segmentation.

### Sizing

- LXC: 4 GB RAM cap + swap, 2–4 cores, ~30 GB root disk on `local-lvm` (SSD).
- Bind-mount `/mnt/pve/wd1tb/nixfact/backups` (HDD) for backup artifacts.
- Onboot enabled.

## Authentication — Authentik OIDC SSO

- **Authentik:** create an OIDC Provider + Application for ERPNext; restrict
  access to an Authentik group (e.g. `erp-users`). Reuses the same Authentik
  instance/pattern as the VPS Nextcloud installs.
- **Frappe:** configure a Social Login Key pointing at Authentik's OIDC
  endpoints → a "Login with Authentik" button; single login, no double prompt
  (Frappe supports OIDC natively, unlike DocuSeal Community).
- Local `Administrator` login retained as break-glass. Signup disabled. Frappe's
  built-in rate limiting / brute-force protection stays on.

## Public ingress — Caddy on the VPS

- Add a site block for `erp.aldewereldconsultancy.nl` →
  `reverse_proxy 192.168.178.X:<web-port>` over the Tailscale subnet route.
- Security headers mirroring the `sign.` block: HSTS preload, X-Content-Type-
  Options nosniff, Referrer-Policy strict-origin-when-cross-origin,
  Permissions-Policy (camera/mic/geo/payment/usb off), hidden Server header.
  Deliberately **no** strict CSP / X-Frame-Options that would break the ERPNext
  desk.
- TLS issued and renewed automatically by Caddy.

## Backups

- **Layer 1 (essential):** cron in the LXC runs
  `bench --site <site> backup --with-files` nightly; output lands on the HDD
  bind-mount `/mnt/pve/wd1tb/nixfact/backups`. Add that path to LXC 200's
  borgmatic `source_directories` so it joins the existing encrypted repo with
  retention (`keep_daily 7 / keep_weekly 4 / keep_monthly 3`).
- **Layer 2 (optional):** weekly PVE `vzdump` of the LXC → `local-pbs`.

## Security

- Unprivileged LXC; `nesting=1` + `keyctl=1` only (via `--with-docker`).
- Secrets (`.env`: DB + Redis passwords) generated by
  `deployment/scripts/generate_env.sh`, stored in `/root/.secrets/nixfact.env`
  on `pro`. Never committed to git.
- Move VPS/Proxmox access to SSH keys; rotate the passwords shared in plaintext
  during this conversation.
- Plan security updates *inside* the LXC (host `unattended-upgrades` does not
  cover guests).

## Open items to verify during planning (not blockers)

1. **Site initialization.** The compose starts services but likely does not
   create the Frappe site or install the apps. Inspect the `Dockerfile` /
   entrypoint; if absent, add a one-time init step: `new-site` →
   `install-app erpnext` → `install-app nixfact_integration` → set admin
   password.
2. **ERPNext version.** Repo is a 17.x fork (the old `docs/installation.md`
   still says version-15). Deploy the repo version the `Dockerfile` builds;
   confirm what that build produces.
3. **Exact web-port bind and Caddy upstream** — reconcile with the generated
   `.env` (`HTTP_PORT`, `SITE_NAME`) and the LXC's actual LAN IP.

## Acceptance criteria

- `https://erp.aldewereldconsultancy.nl` loads the ERPNext desk over valid TLS.
- Login via Authentik OIDC works in a single step; access limited to the chosen
  Authentik group; `Administrator` break-glass still works.
- NixFact Instellingen (and the NixFact doctypes) are present and usable.
- Scheduler enabled; background workers process jobs.
- A nightly backup artifact appears on the HDD bind-mount and is captured by the
  borgmatic run on LXC 200.
- The LXC starts on boot and survives a host reboot.
- Host RAM headroom remains healthy with the trimmed limits under real usage.
