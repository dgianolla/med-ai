---
# Identidade da campanha (obrigatórios)
campaign_id: [slug único em snake_case — também é o nome do arquivo sem .md]
campaign_name: [nome exibido ao agente e à triagem]

# Ciclo de vida
status: active            # active | paused | draft
priority: 50              # 0..100 — usado para desempate na triagem
valid_from:               # opcional, ISO yyyy-mm-dd
valid_until:              # opcional, ISO yyyy-mm-dd

# Origem e oferta
source:                   # meta_ads | google_ads | indicacao | etc.
especialidade:            # especialidade principal, ou vazio
offer_anchor:             # oferta resumida ou valor ancora (substitui o antigo `valor`)
handoff_target: scheduling  # scheduling | commercial | human | none

# Promessas (entram no contexto estruturado como L4)
allowed_promises:
  - "promessa explicitamente autorizada 1"
forbidden_promises:
  - "promessa proibida 1"
  - "promessa proibida 2"
---

## Sobre a campanha

Descreva aqui a campanha real de Ads:
- qual é o objetivo comercial
- qual é a oferta principal
- qual é o público-alvo
- qual dor ou motivação essa campanha captura
- qual contexto geográfico/comercial importa

Este arquivo é a camada L4 (Active Campaign Context). **NÃO** escreva aqui:
- tom de voz, persona, linguagem (pertencem a L2 — prompts/campaign.md)
- regras globais como "nunca invente preço" ou "use get_clinic_info para fatos"
  (pertencem a L3 — prompts/_business_rules.md)
- regras de segurança clínica, urgência ou ideação suicida
  (pertencem a L1 — prompts/_safety.md)

## Fluxo de atendimento

### 1. Qualificação
- Defina como iniciar quando o lead chega por saudação genérica.
- Defina como iniciar quando ele menciona diretamente a campanha, o tema ou a oferta.
- Liste as perguntas de descoberta na ordem.
- Depois de cada pergunta importante, descreva o objetivo comercial ou clínico da pergunta.
- Se alguma informação já tiver sido dada pelo paciente, não repita a pergunta.

### 2. Apresentação da oferta
- Explique como ancorar valor antes de falar preço.
- Deixe claro como a oferta deve ser apresentada: consulta, pacote, protocolo, combo ou exame.
- Se a campanha tiver itens inclusos, liste aqui o que pode ser mencionado.
- Se preço, itens inclusos, parcelamento, protocolo, disponibilidade, convênio ou detalhes operacionais dependerem da base oficial, use `get_clinic_info`.
- Se a campanha exigir comparação entre opções, descreva quando isso pode acontecer.
- Se houver gatilhos sutis de avanço, registre aqui como usar sem pressão artificial.

### 3. Próximo passo
- Defina o que caracteriza avanço real ou confirmação de interesse.
- Se a campanha fechar em agendamento, encerre com: "Vou te encaminhar para agendamento."
- Liste quais dados mínimos podem ser coletados nesta etapa.
- Liste quais dados não devem ser coletados neste agente.
- Defina como agir se o paciente pedir para pensar.
- Defina como agir se o paciente sair do contexto da campanha.

## Escalonamento específico da campanha

- Quando interromper o fluxo comercial desta campanha especificamente.
- Quando encaminhar para humano por motivo de campanha (fora das regras globais de L1).
- Se houver alerta clínico específico, escreva a frase exata de segurança.

## Observações operacionais

- O arquivo de campanha define COMO conduzir esta conversa específica.
- A base de conhecimento define os dados factuais da oferta.
- O handoff precisa carregar contexto suficiente para o próximo agente continuar sem reapresentação.
