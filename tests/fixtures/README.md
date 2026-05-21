# Test Fixtures

Fixture sets are grouped by privacy level and by assignment scenario.

- `private/`: local-only real or sensitive materials. This directory is ignored by Git.
- `public/`: sanitized sample materials that may be committed for GitHub users.

Tests should prefer a private fixture set when it exists locally and fall back to the matching public fixture set when running from a clean clone.

## Fixture Layout

Use the same purpose-based layout for public and private fixture sets:

```text
<fixture_set>/
  assessment_materials/
  answer_key_sources/
  submission_evidence/
```

Fixture files should be classified by purpose, not only by extension. A PDF, text file, code file, spreadsheet, archive, or other artifact may represent assignment material, an answer key source, a learner submission, or a reference solution depending on context.

## Public Fixtures

Public fixtures must be synthetic, sanitized, and safe to commit.

Do not commit:

- real student data
- private answer keys
- private prompts
- credentials or API keys
- confidential teaching materials
- unpublished evaluation datasets

## Private Fixtures

Private fixtures are for local-only testing with sensitive or real-world materials. Keep them ignored by Git and avoid documenting personally identifying source details in tracked files.
