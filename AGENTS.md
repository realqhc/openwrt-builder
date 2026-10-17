# Repository instructions

## Publication boundary

Only generic, reusable project information may be uploaded or published. Do not
upload any user-specific local configuration or information derived from it.
This applies to Git commits and pushes, pull requests, issues, comments, CI logs,
release assets, artifacts, shared chats, and other external services.

Never publish:

- Router runtime configuration, UCI exports, configuration backups, recovery
  archives, filesystem snapshots, or generated proxy/server configurations.
- Passwords, tokens, private keys, credentials, tunnel identities, session data,
  certificates belonging to the user's environment, or authentication material.
- Private IP addresses, network topology, personal hostnames/domains, device
  identities, account details, or paths identifying the user's local environment.
- Local audit results, maintenance plans, diagnostic logs, screenshots, or
  reports containing or derived from the above information.
- Editor settings, local application settings, SSH/cloud configuration, or other
  machine-specific files.

Do not treat prior authorization to build, debug, commit, push, publish firmware,
or schedule maintenance as permission to publish local information. If a task
would require such an upload, do not perform it; explain the conflict and use a
local-only alternative. Renaming files, encoding values, or removing obvious
secrets does not make a local configuration safe to publish.

## Allowed content and review

Generic source code, reusable build scripts, documentation, synthetic test
fixtures, and device build selections may be published only after checking that
they contain no user-specific configuration or data. OpenWrt build-selection
files are distinct from exported router runtime configuration; inspect their
contents rather than relying on the filename or extension.

Firmware and generated build metadata may be published only when produced from
generic sources and free of local configuration, credentials, and private files.
Never copy local router files, backups, or audit directories into firmware
overlays, CI inputs, or release directories. Review the actual upload file list.

Before every commit or upload:

1. Inspect the complete file list and relevant contents, including generated
   files and archive members. Check tracked files as well as untracked files;
   `.gitignore` does not protect files already tracked by Git.
2. Stage or upload an explicit allowlist of reviewed files. Do not use broad
   commands such as `git add .` or upload the entire workspace.
3. Keep local evidence and configuration outside publication paths. Use
   synthetic examples written from scratch when documentation or tests need
   configuration examples.
4. If uncertain whether content is generic, keep it local. Do not print private
   configuration into CI output, public reports, or external tool payloads.

Keep user-specific audit and maintenance material local, with restrictive file
permissions. Do not delete local backups or rewrite Git history merely to hide
an accidental disclosure; stop further publication and report the issue first.
