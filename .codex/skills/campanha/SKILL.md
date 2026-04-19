---
name: campanha
description: Use when the user wants to create, structure, draft, or prepare a new MetaDS campaign for this project, especially when they say /campanha, "nova campanha", "subir campanha", or ask for the Markdown pattern to register an active campaign. Return the project-standard campaign Markdown compatible with backend/campaigns/*.md.
---

# Campanha

Use this skill when the user wants the Markdown base for a new campaign.

## Goal

Return a Markdown template that matches the exact pattern used by the project in `backend/campaigns/*.md`.

The primary job of this skill is to give the user a ready-to-edit campaign draft, following the current project schema instead of inventing a simplified one.

## Output rule

Default to returning a complete Markdown draft inside a fenced `md` block.

If the user gave enough context, pre-fill the draft.
If important information is missing, keep placeholders such as `[nome da campanha]` rather than blocking.

## Required format

The draft must follow these rules:

- Use simple YAML frontmatter with one value per line.
- Prefer the campaign frontmatter currently used by the project:
  - `campaign_id`
  - `campaign_name`
  - `status`
  - `priority`
  - `source`
  - `especialidade`
  - `offer_anchor`
  - `handoff_target`
  - `forbidden_promises`
- `forbidden_promises` should be a YAML list when the user provides concrete prohibitions.
- Additional keys should only be used when the user explicitly asks for them or when the repository pattern already uses them.
- Keep the body in Portuguese.
- Preserve the campaign sections below in this order when the user is asking for the project-standard operational campaign:
  - `## Sobre a campanha`
  - `## Opções de atendimento` when the campaign has named offers, packages, or price tiers
  - `## Nomenclatura obrigatória` when the campaign depends on terminology rules
  - `## Steps de atendimento`
  - `## Escalonamento`

## Campaign body pattern

Inside `## Steps de atendimento`, keep the campaign structured in explicit steps whenever the user provides a step-by-step script.

For campaigns in the newer pattern, prefer:

- `### STEP 1 — [nome]`
- `### STEP 2 — [nome]`
- additional `STEP`s as needed
- quoted example messages when the user already defined them
- operational bullets below each step when needed

If the user instead asks for the generic project campaign pattern, you may still use:

- `### 1. Qualificação`
- `### 2. Apresentação da oferta`
- `### 3. Próximo passo`

But when the user gives a more specific structure, preserve that structure instead of collapsing it.

## Writing guidance

- Stay practical and operational.
- Do not invent prices, exams, benefits, or guarantees that the user did not provide.
- Use placeholders when details are missing.
- Prefer concise bullets the user can edit quickly, but preserve longer quoted scripts when the campaign already includes approved wording.
- Keep the style consistent with the existing campaign files in this repository.
- If the user provides a full campaign in Markdown-like form, convert it to the repository format with minimal rewriting.

## When the user asks only for the pattern

Return the base template from `references/template.md`.

## When the user provides campaign context

Fill what you can:

- campaign id and display name
- source and specialty
- offer anchor
- handoff target
- forbidden promises
- audience and campaign objective
- named offer options, if any
- terminology constraints, if any
- step-by-step sales flow
- escalation situations

## If the user asks to create the file too

After drafting the Markdown, save it as a new file in `backend/campaigns/<slug>.md`, where `<slug>` is a lowercase snake_case version of the campaign name.
