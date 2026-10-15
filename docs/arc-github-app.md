---
title: ARC GitHub App authentication security review
updated: 2026-10-16T01:39:48+09:00
type: runbook
status: current
---

# ARC GitHub App authentication

## Authority and current status

GitHub App is the user-selected long-term direction. This document is preparation
and security review only. No App creation, installation, private-key input,
credential access, runner registration or CI execution is authorized by this text.
The independently approved controller/foundation rollout does not authorize them.
A separate explicit approval has since covered App creation/installation only.
The private App and exact two-repository installation were read back successfully;
no private key was generated/read/input and no runner or CI has executed.

Keep the ARC App separate from the existing Argo CD repository-access App. Do not
change that App's permissions, key or installation. Never print, request in chat,
copy into reports, or hash private-key/PAT/SSM/Secret values.

## Precise proposed grant

- Owner: the personal account KKamJi98. The dedicated private ARC App was created
  only after the exact separate approval and a duplicate-name check. Real App and
  installation identifiers are kept out of this public runbook.
- Installation restricted to exactly KKamJi98/kkamji-platform and
  KKamJi98/binance-quant-lab, never all repositories or an organization-wide pool.
- Repository Administration read/write, required by repository runner registration,
  plus Metadata read. No Contents write, Actions write, Packages write or
  organization Self-hosted runners permission is proposed for registration.
- Private installation on the owner account. No webhook/callback endpoint or
  general user OAuth flow is needed for the proposed server-to-server ARC use.
- App creation/installation approval is complete. The private-key delivery path
  and registration/light canary still need their exact security confirmation.
  A review intent, App installation or successful render is not that confirmation.

Personal-account GitHub Apps and repository registration using App installation
access tokens are documented. The current ARC walkthrough uses organization
examples. Verify the actual personal-account ARC integration with separately
approved real light canaries; do not infer compatibility or scheduling entitlement
from a public API example or the legacy hosted billing annotation alone.

## Shared authority, not credential isolation

One App installed on both repositories shares its private-key authority. Separate
Kubernetes Secrets or SSM copies do not isolate that authority. App compromise
can affect both selected repositories. Do not describe duplicate Secrets as
repository credential isolation or reuse this App for the production publisher.

Job Pods must keep no API token, no management Secret mount/env and no RoleBinding.
Only trusted ARC management components may use registration credentials. Namespace
separation is not VM isolation and does not remove node/kernel escape risk.

## Proposed private-key storage and input

Prefer one canonical SSM SecureString at /kkamji/arc/github-app and one ESO target
Secret ci-pr/arc-github-app-auth, referenced by both scale sets. This reduces
rotation drift, not authority scope. These names are proposals, not resources
already created or an approved change to the two legacy disabled PAT references.

ARC's App credential data keys are github_app_id, github_app_installation_id and
github_app_private_key. Record only non-secret App/installation/key identifiers,
SSM parameter type/version/key metadata and ESO Ready status in operational notes.
No real identifiers or key values belong in this public runbook.

After explicit approval the owner generates/delivers the key through a secure
operator UI/secret-entry flow directly into encrypted storage. Do not pass key
material through chat, screenshots, CLI argv, Helm values, source files or CI logs.
Do not query Kubernetes Secret data or SSM GetParameter(s) to validate delivery.

Existing ESO store Ready is not proof of access to a new path. Confirm the actual
ESO principal, exact SSM resource and customer-managed KMS key/conditions using
metadata. An unrelated local CLI identity is not proof of ESO authorization.
Any principal/path/key permission delta needs separate approval; no wildcard
IAM/KMS expansion or credential extraction is allowed.

The old disabled arc-platform-auth/arc-bql-auth references are not instructions
to create PATs. Replace their wiring only under the approved App input scope.
Do not delete Secret/ExternalSecret objects casually: creationPolicy Owner can
garbage-collect target Secrets even with deletionPolicy Retain.

## Rotation

1. Confirm the operator and approved maintenance/registration scope. Keep a
   non-secret record of the active GitHub key identifier and SSM version.
2. Owner creates a replacement App key securely, preserving the old key briefly
   when it is not compromised. Update the single canonical encrypted parameter
   without revealing either value.
3. Observe ESO metadata/Ready and the management rollout/reload behavior supported
   by the pinned ARC version. Secret Ready alone is not proof that ARC used the
   new key. After separately approved registration/testing, verify fresh auth and
   both light canaries before declaring rotation successful.
4. Owner revokes the old key only after verified cutover. Do not assume deleting
   a private key immediately revokes already issued installation tokens. Follow
   GitHub's documented token/installation revocation controls when needed.
5. Record identifiers, versions, outcomes and cleanup, never key/token values.

## Recovery

Separate invalid/revoked key, removed installation, insufficient repository grant,
ESO/KMS access, network and GitHub service failures. Do not keep retrying a legacy
billing annotation or request paid CI. Preserve failure metadata without secrets.

Pause new dispatch/registration under the approved incident scope, drain/cancel
jobs and retain the controller for finalizers/deregistration. A compromised key
requires revocation and a new key, not restoration of the compromised version.
Owner-controlled restoration of a non-compromised encrypted version is a separate
approved secret operation. Do not extract it into terminal output as a shortcut.

Keep namespaces/CRDs and unrelated workloads intact. Do not force-remove cleanup
finalizers or enable privileged/unconfined execution to recover authentication.
After owner input, recheck ESO metadata, actual ARC auth, repository scope and
separately approved light canaries. Do not claim full CI from those canaries.

## Official sources

- [ARC authentication](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/authenticate-to-the-api)
- [Personal-account App registration](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
- [Repository registration token API](https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository)
- [App installation access tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
- [ESO lifecycle rules](rules/external-secrets.md)
- [ARC rollout](arc-ci.md)
