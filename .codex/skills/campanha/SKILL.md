---
name: campanha
description: Use when the user wants to create, structure, draft, or prepare a new MetaDS campaign for this project, especially when they say /campanha, "nova campanha", "subir campanha", or ask for the Markdown pattern to register an active campaign. Return the project-standard campaign Markdown compatible with backend/campaigns/*.md.
---

# Campanha

Use this skill when the user wants the Markdown base for a new campaign.

## Goal

Return a Markdown template that matches the exact pattern used by the project in `backend/campaigns/*.md`.

The primary job of this skill is to give the user a ready-to-edit campaign draft, not to invent a new schema.

## Output rule

Default to returning a complete Markdown draft inside a fenced `md` block.

If the user gave enough context, pre-fill the draft.
If important information is missing, keep placeholders such as `[nome da campanha]` rather than blocking.

## Required format

The draft must follow these rules:

- Use simple YAML frontmatter with one value per line.
- Only use these frontmatter fields: `nome`, `especialidade`, `valor`.
- Do not use lists, nested objects, or extra keys in the frontmatter.
- Keep the body in Portuguese.
- Preserve the campaign sections below in this order:
  - `## Sobre a campanha`
  - `## Fluxo de atendimento`
  - `## Não dizer`
  - `## Escalonamento`

## Campaign body pattern

Inside `## Fluxo de atendimento`, always keep:

- An opening instruction telling the agent to follow the steps in order.
- A rule to ask one question at a time in WhatsApp style.
- `### 1. Qualificação`
- `### 2. Apresentação da oferta`
- `### 3. Próximo passo`

The `Próximo passo` section should usually include:

- `Se o paciente confirmar interesse em agendar, encerre sua fala com: "Vou te encaminhar para agendamento."`

If the campaign has special handoff rules, include them there or in `## Escalonamento`.

## Writing guidance

- Stay practical and operational.
- Do not invent prices, exams, benefits, or guarantees that the user did not provide.
- Use placeholders when details are missing.
- Prefer concise bullets the user can edit quickly.
- Keep the style consistent with the existing campaign files in this repository.

## When the user asks only for the pattern

Return the base template from `references/template.md`.

## When the user provides campaign context

Fill what you can:

- campaign name
- specialty
- price or price rule
- target audience
- offer included
- qualification questions
- offer presentation rules
- handoff rule for scheduling
- forbidden claims
- escalation situations

## If the user asks to create the file too

After drafting the Markdown, save it as a new file in `backend/campaigns/<slug>.md`, where `<slug>` is a lowercase snake_case version of the campaign name.
