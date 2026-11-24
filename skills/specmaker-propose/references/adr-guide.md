# ADR Guide: which decisions to record

An ADR records one significant decision: the options, the trade-off, and the
reason. It outlives the change, because the archive step copies it into the
project-wide log at `specmaker/adrs/`. Reviewers treat accepted ADRs as
settled. They check that the design complies with an ADR rather than reopening
it, which keeps reviews from going in circles.

## Write an ADR when the decision is

- **new**: `project.md` says nothing about it, or
- **a change**: it departs from `project.md` or from an earlier accepted ADR
  (mark the old one `Superseded by ADR-NNNN`), and
- **costly to reverse**: it would take more than a few days to undo, or it
  affects other teams, data, security or money.

Skip an ADR when `project.md` already settles the choice or it is cheap to
reverse. Record such choices in the LLD.

## Topics to consider

Go through this list in the section plan. For each topic: does this change make
a new or changed decision here?

| Topic | Typical questions | Typical options |
|---|---|---|
| Language and runtime | New service in a different language? Runtime version? | Team's existing language vs a better-suited one |
| Application framework | Web, CLI, UI or worker framework? | Framework A vs B vs none |
| Persistence | Store, schema ownership, consistency, retention | Relational vs document vs key-value; shared vs dedicated database |
| Messaging and integration | Synchronous or asynchronous? Delivery guarantees? | REST vs gRPC vs queue vs event stream |
| API style and versioning | Public contract, compatibility promise | REST/OpenAPI, GraphQL, gRPC; URL vs header versioning |
| Identity and access | AuthN provider, AuthZ model, service-to-service trust | OIDC provider, RBAC vs ABAC, mTLS vs tokens |
| Hosting and topology | Where it runs; how it scales; regions | Serverless vs containers vs VMs; single vs multi-region |
| Infrastructure as code | How environments are created | Terraform, Pulumi, CDK, Helm, none |
| CI/CD and release | Pipeline, environments, promotion, rollback | Trunk-based with flags vs release branches; blue-green vs canary |
| Configuration and secrets | Where config and secrets live | Env vars, vault, cloud secret manager |
| Observability | Logs, metrics, traces, alerting | OpenTelemetry plus backend X; SLOs |
| Testing approach | Test levels, tooling, test data | Contract tests, end-to-end framework, fixtures vs factories |
| Packaging and distribution | How users get it | Container image, package registry, installer, app store |
| Build vs buy | Use an existing product or library? | Library or service X vs in-house |

## Writing it

- At least two real options. "Do nothing" counts when it is viable.
- Name the decision drivers first, then judge each option against them. An ADR
  that names drivers after choosing is a rationalisation; reviewers will flag
  it.
- Put costs in numbers where possible: money, effort in days, latency.
- Consequences include the negative ones, and what would make you revisit the
  decision.
- Only the user accepts an ADR. Set `Status: Accepted` after they agree, and
  record it in the ledger.
