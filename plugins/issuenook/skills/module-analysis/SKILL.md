---
id: module-analysis
name: module-analysis
title: "Module Analysis Skill Template"
summary: "Abstract scaffolding for authoring a module/component analysis skill used by Issuenook code-analysis and hypothesis-verification phases."
tags:
  - issuenook
  - skill
  - template
  - code-analysis
---

# Module Analysis Skill Template

Use this template to author a domain-specific analysis skill for a
module, service, component, or subsystem.

## When to author one

Create a per-module analysis skill when a module has:

- log-prefix conventions or signature patterns;
- a non-trivial state machine;
- recurring known-issue fingerprints;
- module-specific review or verification criteria.

## Directory layout

Place each new skill in one of:

- `.codenook/memory/skills/<module>-analysis/SKILL.md` for
  deployment-specific or team-specific skills;
- `<plugin>/skills/<module>-analysis/SKILL.md` only when the skill is
  generic enough to ship with a plugin.

## Frontmatter contract

```yaml
---
id: "<slug>"
name: "<slug>"
title: "<Human title>"
summary: "<one-paragraph purpose>"
tags:
  - "skill"
  - "<module>"
  - "analysis"
---
```

Do not add unsupported frontmatter fields.

## Recommended body sections

1. Module overview.
2. Log patterns.
3. State machine / normal flow.
4. Error handling and retry semantics.
5. Known issues and fingerprints.
6. Review checklist.
7. Verification checks.

Every claim should be traceable to code, logs, documentation, or a
completed case record.
