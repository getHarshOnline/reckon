# Planned evaluation contract

This specification describes a future evaluator that runs an experiment against fixed, permitted inputs and returns an immutable signed result. It is separate from the implemented [laboratory metrics](11-Evaluation-Metrics.md).

> [!NOTE]
>
> **Proposed.** Its manifest schema, wire identifier and signing implementation have not been published.

## Inputs and permissions

An evaluation receives two immutable inputs: the experiment owner's manifest and one permitted dataset, corpus version with its use record, or owner-supplied export. It does not discover a wider database, store, model, route or purpose at runtime. Refuse inputs that are unknown, floating, widened, stale, expired, incompatible with the rights, over budget or of the wrong provenance before execution.

The profile must specify how a change in permission reaches a running evaluation and how affected work stops or is isolated. Frozen input bytes remain fixed. Before delivery, check current permission for the exact artifact and recipient. Retained evidence keeps its original limits; a new comparison or promotion needs its own current permission.

## Experiment manifest

The manifest fixes:

- The question and permitted operations.
- Identities and hashes of experiment, candidates, baselines, code, model, runtime and any corpus version.
- Sources and dataset splits; interventions or probes declared in advance.
- Causal assumptions and falsifiers where a causal interpretation is sought.
- Metrics, uncertainty, the margin that counts as a difference, resource and latency budgets, iteration limits and stopping rule.
- Treatment of missing or failed evidence, redaction and output policy, result schema and signer.
- The kind of artifact being changed and its full base: package and program dependencies, policy/content packs, model and runtime profile, application releases, compiled generation, the evidence available through the stated point, owner revisions and decision environment.
- Separate permission to run on sources, retain context, evaluate, train or fine-tune, derive a model, generalise and publish.
- Each evaluator's exact version, configuration and role, including whether it generated candidates, rewards or evidence for selection and promotion.

If an evaluator generated a candidate or its reward, its evidence alone cannot justify promotion. Keep generation, evaluation and the owner's decision distinct.

## Result and signature

The result records profile and experiment references, input digest and corpus-use record, ordered candidates and baselines, actual operations, measurements and uncertainty, costs, violated assumptions, failed/unknown/omitted cases, reproduction requirements, limited diagnostic views, redaction summary and signer. Reckon must publish its identifier and manifest; consumers cannot invent equivalent wire definitions.

The signing contract must define canonical bytes, authorised signer, key lifecycle and exactly what the signature authenticates. Test a valid signed result as the control. A result without its runtime signature must fail even beside a valid release attestation. Changed result bytes under the original signature must also fail.

Diagnostic access is limited to observable artifacts explicitly permitted by the experiment's privacy, rights, capability and resource limits. It must not request hidden chain-of-thought, private prompts, credentials, unrestricted activations or state, or anything outside the permitted input.

## Comparisons

Report repeatability, independence, grounding and coverage separately. Preserve incomplete coverage and disagreement. Two reviewers, when required, receive the same fixed candidate, rubric and evidence; record their actual independence rather than inferring it from having two outputs.

For cross-version interpretation, bind the original signed artifact references and digests, question, matched case revisions, permitted replay inputs and common measure. Changed rubrics, shifted coverage or missing replay inputs may leave the claim unresolved. A separately permitted matched-subset comparison supports only its declared question.

Before relying on that interpretation, a consumer checks the exact artifacts and question and its current permission to use them. A result for a different revision or narrower question does not satisfy the requested comparison. Retain original references and the consumer's decision under the applicable retention policy. Who issues cross-version interpretations remains unresolved.

## Pale coordination-learning profile

Read Pale's evaluation-runner manifest by reference. It defines evaluation order and binds the base compiled generation; candidate owner and digest; evidence coordinates; evaluators, roles, profiles, budgets and order; required coordinates; verification results from the owning products; release state; outcome vocabulary; output references; whether an owner ruling is required; and invalidation conditions.

Reckon keeps its result. Pale keeps references, obligations and its own recorded outcome, without copying the evaluator's database. For a SkillOpt-produced candidate, validate candidate, evidence, origin and independence fields without invoking the search or reading its store.

Check the manifest's search-exposure references against the protected comparison split. If search feedback or a related case influenced selection, treat that evidence as tuning. Unknown exposure leaves independence unresolved.

## Scope edit-history projection

A proposed record would carry the projection schema ID/hash and record ID; source proposal schema/reference/hash; whether it is only proposed, decided or released; decision and release references/hashes when present; evidence delta; projection-policy reference/hash; generation time; issuer principal, key ID and epoch; signing-authority binding; canonical projection hash; and signature.

The contract must define owner authority, dependency closure, canonical form, permitted schemas, key lifecycle and rejection of restored older state. Add fixtures for wrong mode, deployment, dependency closure, schema, key and source version. These fields are proposals until the contract is published.

The projection is evidence about Scope's edit history. Reckon cannot change, accept, reject or release the original. A later corpus case sits alongside the source record and does not replace it. Outcome differences earn a causal interpretation only when the experiment meets its causal-evidence standard.

## Refusal and containment cases

An artifact must say ablation attribution or intervention contrast unless the causal-evidence profile is met. The implemented `ABLATION` credit policy uses positive measured deltas; names such as `CausalScore` still appear in the laboratory, but establish no causal interpretation. Test that a bare ablation delta, influence proxy, enum name or normalised score cannot acquire a causal label merely by passing through an API. Earlier saved records keep their original vocabulary and source revision.

Test direct access to another owner's store, mixed provenance, split leakage, undeclared data or operations, forged manifests or exports, stale source evidence, budget overruns, missing uncertainty, hidden-reasoning or private-payload requests, causal overclaims and profile confusion.

The evaluator must not emit a proposal or candidate, train or fine-tune, choose a seat occupant or provider, admit a capability, publish a model, or write, release, compile or activate a profile. It is not the live judge in a host event. Tests must establish those refusals as well as successful evaluation.
