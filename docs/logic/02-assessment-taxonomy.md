# Assessment Taxonomy Logic

This document describes the public assessment taxonomy logic for RubriCore-STE. It defines classification vocabulary and compatibility boundaries. Durable identity, provenance, storage, and lifecycle rules belong in [Setup Database Logic](01-setupdb.md).

## Core Boundary

Assessment taxonomy is for classification and compatibility. It describes what kind of task is being evaluated, what evidence can be accepted, what output shape is expected, and which rubric styles are appropriate. It is not the source of operational identity, persistence, ownership, upload history, release state, attempt history, or audit history.

Assessments should be classified by task type rather than by subject identity. A durable assessment record may contain many assessment items, and each item may have its own task type, output type, answer key, rubric mapping, and grading policy. The taxonomy gives those records stable classification terms; the database gives them IDs and lifecycle.

## Taxonomy Concepts

RubriCore-STE does not organize its core model around fixed roles, professions, or subjects. The platform is centered on reusable assessment primitives:

- **Assessment type**: the nature of the task being evaluated.
- **Evidence type**: the form of student work submitted.
- **Output type**: the expected shape of the response or produced work.
- **Rubric type**: the scoring structure used for evaluation.
- **Subject pack**: portable configuration for a discipline or curriculum area.

Subject-specific behavior belongs in subject packs. Core grading, review, versioning, and audit workflows remain generic.

## Assessment Types

Supported assessment types may include:

- quiz or multiple-choice question
- numeric answer
- short answer
- constructed response
- code assignment
- project
- lab report
- oral explanation
- art or visual critique
- mixed-format task

New assessment types should be added through configuration and clear interfaces, not by changing the platform's core assumptions.

## Evidence Types

RubriCore-STE supports different forms of evidence because learning can be demonstrated in many ways.

Supported evidence types may include:

- text
- numeric input
- code
- file upload
- image
- audio
- video
- table data
- mixed evidence bundles

Evidence should be stored in its original form where appropriate, with extracted or normalized representations stored separately for grading, review, and traceability.

Evidence taxonomy should not decide whether a submitted file is valid, correct, late, owned by a learner, attached to a particular assessment, or ready for grading. Those decisions require submission records, artifact records, policy, extraction status, grading context, and audit history.

## Rubric Types

Rubrics define how work is evaluated. RubriCore-STE should support multiple rubric styles, including:

- **Binary key**: correct or incorrect scoring.
- **Checklist**: required elements are present or absent.
- **Analytic rubric**: multiple criteria scored independently.
- **Holistic rubric**: one overall score based on the whole response.
- **Criterion-weighted rubric**: criteria have explicit weights.

Rubrics should be versioned, explainable, and connected to the evidence they evaluate. The implemented rubric framework is described in [Rubric Framework Logic](03-rubric-framework.md).

Rubric taxonomy classifies the scoring structure. Published rubric versions, criteria, performance levels, descriptors, bindings, answer key versions, source materials, and grading results are persistent database records and must remain traceable over time.

## Taxonomy Mapping

Taxonomy concepts map to operational records as follows:

| Taxonomy concept | Operational use |
| --- | --- |
| Assessment type | Classifies an assessment or assessment item as a task shape such as code assignment, numeric answer, lab report, or project |
| Evidence type | Classifies submitted evidence such as text, numeric value, code, image, archive, or mixed bundle |
| Output type | Describes the expected output or response shape, such as exact answer, executable behavior, report, table, or presentation |
| Rubric type | Describes the scoring structure, such as binary key, checklist, analytic rubric, holistic rubric, or weighted criteria |
| File purpose | Describes why an artifact exists in the workflow, such as assessment material, answer key source, submission evidence, rubric source, or converted Markdown |
| Compatibility rule | Checks whether an assessment type can reasonably pair with an evidence type, output type, or rubric type |

Taxonomy compatibility should prevent obvious mismatches, such as grading an image as a numeric answer unless a subject pack or explicit configuration allows that behavior. Compatibility rules should remain explainable and configurable rather than becoming hidden subject-specific workflows.

## Non-Taxonomy Concerns

IDs, timestamps, ownership, attempts, upload sessions, course releases, grading runs, review tasks, and audit events are not taxonomy concerns. These belong to the database and application lifecycle model.

For example, `code-assignment` is a taxonomy value. A specific assignment named "Python Score Summary", its questions, learner submissions, uploaded files, grading runs, and teacher overrides are persistent records with their own IDs and history.

## Persistence Boundary

Taxonomy docs define the vocabulary and compatibility rules for assessment design. Database setup docs define durable identity, provenance, linkage, lifecycle, and auditability.

The boundary should stay clear:

- taxonomy answers "what kind of assessment, evidence, output, or rubric is this?"
- database design answers "which exact assessment, item, learner, submission, artifact, grading run, and review decision is this?"
- rubric framework logic answers "which criteria, score bands, descriptors, version, and binding define the scoring context?"
- subject packs may recommend taxonomy combinations and adapters, but they should not replace durable database relationships
- grading should store both classification context and persistent IDs so future review can explain what was graded and why
