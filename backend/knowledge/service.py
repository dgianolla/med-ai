"""
Serviço centralizado de conhecimento da clínica.
Lê arquivos JSON e serve dados estruturados para os agentes.
"""

import json
import logging
from pathlib import Path
from typing import Any
from functools import lru_cache

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent


class KnowledgeService:
    """Carrega e serve conhecimento da clínica com cache em memória."""

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._loaded = False

    def _load_all(self) -> None:
        """Carrega todos os arquivos JSON na inicialização."""
        if self._loaded:
            return

        for filename in KNOWLEDGE_DIR.glob("*.json"):
            key = filename.stem  # clinic_info, professionals, pricing
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    self._cache[key] = json.load(f)
                logger.info("Knowledge loaded: %s", filename.name)
            except Exception as e:
                logger.error("Erro ao carregar knowledge/%s: %s", filename.name, e)
                self._cache[key] = {}

        self._loaded = True

    # ----------------------------------------------------------------
    # API pública
    # ----------------------------------------------------------------

    def get(self, category: str, path: str | None = None) -> Any:
        """
        Retorna dado de conhecimento por categoria e caminho opcional.

        Exemplos:
            get("clinic_info")                    → tudo
            get("clinic_info", "address")         → só endereço
            get("pricing", "combos")              → lista de combos
            get("pricing", "combos.0.price")      → preço do primeiro combo
            get("professionals", "convenios")     → lista de convênios
        """
        self._load_all()

        if category not in self._cache:
            logger.warning("Categoria de conhecimento desconhecida: %s", category)
            return None

        data = self._cache[category]

        if not path:
            return data

        # Navega pelo caminho (dot notation)
        keys = path.split(".")
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            elif isinstance(data, list):
                try:
                    data = data[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return data

    @staticmethod
    def _match_faq_entry(query_lower: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Encontra a pergunta mais próxima por interseção simples de palavras."""
        query_words = set(query_lower.split())
        best_match = None
        best_score = 0

        for item in items:
            question = item.get("q", "").lower()
            if not question:
                continue
            score = len(set(question.split()) & query_words)
            if score > best_score:
                best_score = score
                best_match = item

        return best_match if best_match and best_score >= 1 else None

    def search(self, query: str) -> str:
        """
        Busca simplificada por palavras-chave.
        Retorna texto formatado com os resultados.
        Usado pela tool get_clinic_info quando o Claude faz pergunta em linguagem natural.
        """
        self._load_all()
        query_lower = query.lower()
        results = []
        pens_query = any(
            w in query_lower
            for w in ["caneta", "injetável", "injetavel", "ozempic", "mounjaro", "semaglutida", "tirzepatida", "aplicação", "appli"]
        )

        # ============================================================
        # COMBOS E PREÇOS
        # ============================================================
        if any(w in query_lower for w in ["combo", "pacote", "preço", "valor", "custo", "quanto", "custa"]):
            pricing = self._cache.get("pricing", {})
            combos = pricing.get("combos", [])
            if any(w in query_lower for w in ["mulher", "gineco", "papanicolau"]):
                for c in combos:
                    if "mulher" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["homem", "masculino"]):
                for c in combos:
                    if "homem" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["idoso", "third age", "melhor idade"]):
                for c in combos:
                    if "idoso" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["pediatra", "criança", "infantil"]):
                for c in combos:
                    if "pediatria" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["cardio", "coração", "cardiologista"]):
                for c in combos:
                    if "cardio" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            else:
                for c in combos:
                    results.append(f"**{c['name']}** — R$ {c['price']:.2f}")

            protocols = pricing.get("weight_loss_protocols", [])
            if any(w in query_lower for w in ["emagrecimento", "ozempic", "mounjaro", "peso", "protocolo"]):
                for p in protocols:
                    if "price_90_days" in p:
                        results.append(
                            f"**{p['name']}** — R$ {p['price_90_days']:.2f} (90 dias) "
                            f"ou R$ {p['price_monthly']:.2f}/mês"
                        )
                    else:
                        results.append(
                            f"**{p['name']}** — R$ {p['price']:.2f} ({p['duration_days']} dias)"
                        )

            # Check-ups
            pacotes = pricing.get("pacotes_preco", {})
            if pacotes:
                for key, pacote in pacotes.items():
                    if any(w in query_lower for w in ["check", "checkup", "check-up", "básico", "completo"]):
                        results.append(
                            f"**{pacote['name']}** — R$ {pacote['price']:.2f}\n"
                            f"Inclui: {', '.join(pacote['includes'])}\n"
                            f"{pacote.get('savings_note', '')}"
                        )

        # ============================================================
        # CONSULTAS AVULSAS
        # ============================================================
        if any(w in query_lower for w in ["consulta avulsa", "valor da consulta", "preço da consulta", "quanto custa a consulta", "custa a consulta", "custa consulta"]):
            pricing = self._cache.get("pricing", {})
            consultas = pricing.get("consultas_avulsas", [])
            if consultas:
                results.append("**Consultas Avulsas (valores de referência):**")
                for c in consultas:
                    results.append(
                        f"• {c['specialty']} ({c['professional']}) — R$ {c['price_particular']:.2f}"
                    )

        # ============================================================
        # EXAMES AVULSOS
        # ============================================================
        if any(w in query_lower for w in ["exame avulso", "preço do exame", "valor do exame", "quanto custa o exame", "custa o exame", "exames de imagem", "exames laboratoriais"]):
            pricing = self._cache.get("pricing", {})
            exames = pricing.get("exames_avulsos", [])
            if exames:
                # Filtra por categoria se mencionada
                category_filter = None
                if "laboratorial" in query_lower or "sangue" in query_lower:
                    category_filter = "laboratorial"
                elif "imagem" in query_lower:
                    category_filter = "imagem"
                elif "ecg" in query_lower or "mapa" in query_lower or "eletro" in query_lower:
                    category_filter = "procedimento"
                elif "papanicolau" in query_lower:
                    category_filter = "procedimento"

                filtered = [e for e in exames if not category_filter or e["category"] == category_filter]
                results.append("**Exames Avulsos:**")
                for e in filtered:
                    results.append(f"• {e['name']} — R$ {e['price']:.2f}")

        # ============================================================
        # ESPECIALIDADES
        # ============================================================
        if any(w in query_lower for w in ["especialidade", "o que faz", "o que trata", "quando procurar"]):
            specialties = self._cache.get("specialties", {}).get("specialties", [])
            # Tenta encontrar especialidade específica
            target_spec = None
            for spec in specialties:
                if any(alias in query_lower for alias in spec.get("aliases", [])):
                    target_spec = spec
                    break

            if target_spec:
                results.append(
                    f"**{target_spec['name']}**\n"
                    f"{target_spec['description']}\n\n"
                    f"**Quando procurar:**\n" +
                    "\n".join(f"• {w}" for w in target_spec.get("when_to_seek", [])) +
                    f"\n\n**Preparo:** {target_spec.get('preparation', 'Sem preparo especial.')}"
                )
            else:
                # Lista todas
                results.append("**Especialidades disponíveis:**")
                for s in specialties:
                    results.append(f"• **{s['name']}** — {s['description'][:80]}...")

        # ============================================================
        # PREPARO
        # ============================================================
        if any(w in query_lower for w in ["preparo", "preparação", "como se preparar", "jejum", "antes do exame", "antes da consulta", "como se prepar", "preparar"]):
            preparations = self._cache.get("preparation", {}).get("preparos", [])
            # Tenta encontrar preparo específico
            target_prep = None
            for p in preparations:
                if any(w in query_lower for w in [p["type"], p["title"].lower()]):
                    target_prep = p
                    break

            if target_prep:
                prep_text = f"**{target_prep['title']}**\n\n**Preparo:**\n"
                prep_text += "\n".join(f"• {s}" for s in target_prep.get("preparation", []))
                if target_prep.get("restrictions"):
                    prep_text += "\n\n**Restrições:**\n"
                    prep_text += "\n".join(f"⚠️ {s}" for s in target_prep["restrictions"])
                if target_prep.get("exam_specifics"):
                    prep_text += "\n\n**Preparo específico:**\n"
                    for exam, instr in target_prep["exam_specifics"].items():
                        prep_text += f"• {exam}: {instr}\n"
                results.append(prep_text)
            else:
                results.append("**Preparos disponíveis para:**")
                for p in preparations:
                    results.append(f"• {p['title']}")

        # ============================================================
        # FAQ
        # ============================================================
        faq_triggered = False
        if (
            not pens_query
            and any(w in query_lower for w in ["como faço", "posso", "preciso", "tem", "quanto tempo", "o que acontec", "e se", "o que levar", "o que devo", "devo levar", "levar na", "como funciona", "o que é", "o que ", "deve "])
        ):
            faq = self._cache.get("faq", {}).get("faq", [])
            faq_items = []
            for category in faq:
                faq_items.extend(category.get("questions", []))

            best_match = self._match_faq_entry(query_lower, faq_items)
            if best_match:
                results.append(f"**{best_match['q']}**\n\n{best_match['a']}")
                faq_triggered = True

        # ============================================================
        # POLÍTICAS
        # ============================================================
        if any(w in query_lower for w in ["cancelamento", "cancelar", "reagendar", "reagendamento", "falta", "faltou"]):
            policies = self._cache.get("policies", {}).get("policies", {}).get("cancelamento", {})
            if policies:
                results.append(f"**{policies.get('title', 'Política de Cancelamento')}**")
                for rule in policies.get("rules", []):
                    results.append(f"• {rule}")

        if any(w in query_lower for w in ["atraso", "atrasar", "tolerância", "chegar atrasado"]):
            policies = self._cache.get("policies", {}).get("policies", {}).get("atraso", {})
            if policies:
                results.append(f"**{policies.get('title', 'Política de Atraso')}**")
                for rule in policies.get("rules", []):
                    results.append(f"• {rule}")

        if any(w in query_lower for w in ["menor de idade", "criança", "acompanhado", "responsável"]):
            policies = self._cache.get("policies", {}).get("policies", {}).get("menores", {})
            if policies:
                results.append(f"**{policies.get('title', 'Atendimento de Menores')}**")
                for rule in policies.get("rules", []):
                    results.append(f"• {rule}")

        if any(w in query_lower for w in ["lgpd", "dados pessoais", "privacidade", "excluir dados"]):
            policies = self._cache.get("policies", {}).get("policies", {}).get("lgpd", {})
            if policies:
                results.append(f"**{policies.get('title', 'Proteção de Dados')}**")
                for rule in policies.get("rules", []):
                    results.append(f"• {rule}")

        # ============================================================
        # CANETAS INJETÁVEIS / PROTOCOLOS DE EMAGRECIMENTO
        # ============================================================
        if pens_query:
            pens_data = self._cache.get("injectable_pens", {})
            canetas = pens_data.get("canetas_injetaveis", [])
            pens_faq = pens_data.get("perguntas_frequentes", [])

            if any(w in query_lower for w in ["como funciona", "posso", "preciso", "qual a diferença", "diferença", "diferenca", "inclui", "incluído", "incluido", "parcel", "mensal"]):
                best_pen_faq = self._match_faq_entry(query_lower, pens_faq)
                if best_pen_faq:
                    results.append(f"**{best_pen_faq['q']}**\n\n{best_pen_faq['a']}")

            # Tenta encontrar caneta específica
            target_pen = None
            mentioned_pens = [
                c for c in canetas
                if c["id"] in query_lower or c["name"].lower() in query_lower
            ]
            if len(mentioned_pens) == 1:
                target_pen = mentioned_pens[0]

            if target_pen:
                pen_text = f"**{target_pen['name']}** ({target_pen.get('active_ingredient', '')})\n"
                pen_text += f"**Tipo:** {target_pen['type']}\n"
                pen_text += f"**Aplicação:** {target_pen['application']}\n\n"

                protocols = target_pen.get("protocols", [])
                if protocols:
                    pen_text += "**Protocolos disponíveis:**\n\n"
                    for p in protocols:
                        if p.get("available", True):
                            pen_text += f"• **{p['name']}**\n"
                            if "price" in p:
                                pen_text += f"  Valor: R$ {p['price']:.2f}\n"
                            if "duration_days" in p:
                                pen_text += f"  Duração: {p['duration_days']} dias\n"
                            if p.get("includes"):
                                pen_text += f"  Inclui:\n"
                                for item in p["includes"]:
                                    pen_text += f"  - {item}\n"
                            if p.get("note"):
                                pen_text += f"  ⚠️ {p['note']}\n"
                            pen_text += "\n"
                        else:
                            pen_text += f"• **{p['name']}** — {p.get('note', 'Não disponível individualmente')}\n\n"

                requirements = target_pen.get("requirements", [])
                if requirements:
                    pen_text += "**Requisitos:**\n"
                    for r in requirements:
                        pen_text += f"• {r}\n"

                results.append(pen_text)
            else:
                # Lista todas as canetas
                results.append("**Canetas Injetáveis disponíveis:**")
                for c in canetas:
                    results.append(f"• **{c['name']}** ({c.get('active_ingredient', '')})")

                info = pens_data.get("informacoes_gerais", {})
                if info.get("exigencias"):
                    results.append(f"\n**Exigências para ambos os protocolos:**")
                    for e in info["exigencias"]:
                        results.append(f"• {e}")

        # ============================================================
        # CONVÊNIOS (expandido)
        # ============================================================
        if any(w in query_lower for w in ["convênio", "convenio", "plano", "particular", "cobertura"]):
            convenios_data = self._cache.get("convenios", {})
            convenios = convenios_data.get("convenios", [])

            # Tenta encontrar convênio específico
            target_conv = None
            for c in convenios:
                if c["slug"] in query_lower or c["name"].lower() in query_lower:
                    target_conv = c
                    break

            if target_conv:
                conv_text = f"**{target_conv['name']}**\n"
                conv_text += f"**Cobertura:** {', '.join(target_conv.get('coverage', []))}\n"
                conv_text += f"**Coparticipação:** {target_conv.get('coparticipation', 'Consultar')}\n"
                conv_text += f"**Documentos:** {', '.join(target_conv.get('documents_required', []))}"
                if target_conv.get("notes"):
                    conv_text += f"\n\n⚠️ {target_conv['notes']}"
                results.append(conv_text)
            else:
                # Lista todos
                convenio_names = [c["name"] for c in convenios]
                results.append(
                    f"**Convênios aceitos:** {', '.join(convenio_names)}\n\n"
                    f"Para saber detalhes de um convênio específico, me diga qual!"
                )

        # ============================================================
        # INFORMAÇÕES GERAIS DA CLÍNICA
        # ============================================================
        if any(w in query_lower for w in ["horário", "funcionamento", "aberto", "hora"]):
            hours = self._cache.get("clinic_info", {}).get("hours", {})
            results.append(
                f"**Horários de funcionamento:**\n"
                f"Seg–Sex: {hours.get('weekdays')}\n"
                f"Sábado: {hours.get('saturday')}\n"
                f"Domingo e Feriados: {hours.get('sunday_holidays')}"
            )

        if any(w in query_lower for w in ["endereço", "localização", "onde", "local", "fica"]):
            addr = self._cache.get("clinic_info", {}).get("address", {})
            results.append(
                f"**Endereço:** {addr.get('street')}\n"
                f"**Referência:** {addr.get('landmark')}"
            )

        if any(w in query_lower for w in ["pagamento", "pix", "parcela", "débito", "crédito", "dinheiro"]):
            payment = self._cache.get("clinic_info", {}).get("payment", {})
            results.append(
                f"**Formas de pagamento:** {', '.join(payment.get('methods', []))}\n"
                f"**Chave PIX:** {payment.get('pix_key')}\n"
                f"**Parcelamento:** Consultas até 2x | Exames/Combos até 10x (sem juros)"
            )

        if any(w in query_lower for w in ["retorno", "gratuito", "30 dia"]):
            ret = self._cache.get("clinic_info", {}).get("return_policy", {})
            results.append(
                f"**Política de retorno:** Gratuito em até {ret.get('free_return_days')} dias "
                f"da consulta original (com o mesmo médico)."
            )

        if any(w in query_lower for w in ["documento", "rg", "cnh", "levar", "preciso levar"]):
            docs = self._cache.get("clinic_info", {}).get("documents_required", [])
            results.append(f"**Documentos necessários:**\n" + "\n".join(f"• {d}" for d in docs))

        if any(w in query_lower for w in ["jejum", "resultado", "laboratorial"]):
            exam = self._cache.get("clinic_info", {}).get("exam_policy", {})
            results.append(
                f"**Política de exames:**\n"
                f"• Jejum: {exam.get('lab_fasting_hours')}\n"
                f"• Resultado: {exam.get('result_turnaround')}\n"
                f"• Pedido médico: obrigatório"
            )

        if any(w in query_lower for w in ["profissional", "médico", "doutor", "especialidade"]):
            profs = self._cache.get("professionals", {}).get("professionals", [])
            for p in profs:
                specs = ", ".join(s["name"] for s in p["specialties"])
                results.append(f"**{p['name']}** — {specs}")

        if not results:
            return "Não encontrei informações específicas para essa consulta. Posso verificar com a equipe da clínica!"

        return "\n\n".join(results)


# Instância global
_knowledge_service: KnowledgeService | None = None


def get_knowledge() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
