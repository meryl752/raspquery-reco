"""
Fallback déterministe — dernier recours uniquement (RECO_ALLOW_HEURISTIC_FALLBACK=true).
Sous-tâches concrètes par catégorie, pas de copier-coller de l'objectif.
"""

from __future__ import annotations

import re

from app.domain.analyzed_query import AnalyzedQuery, AtomicSubtask, FunctionalDomain, ValidCategory

_KEYWORD_MAP: dict[ValidCategory, tuple[str, ...]] = {
    ValidCategory.SEO: (
        "seo",
        "référencement",
        "referencement",
        "google",
        "serp",
        "trafic",
        "backlink",
        "rank",
    ),
    ValidCategory.COPYWRITING: (
        "texte",
        "rédiger",
        "rediger",
        "contenu",
        "article",
        "copywriting",
        "copy",
        "blog",
        "newsletter",
        "fiche produit",
    ),
    ValidCategory.AUTOMATION: (
        "automatiser",
        "automation",
        "zapier",
        "make",
        "n8n",
        "workflow",
        "integromat",
        "boutique",
        "shopify",
        "e-commerce",
        "ecommerce",
    ),
    ValidCategory.PROSPECTING: (
        "prospect",
        "prospection",
        "outreach",
        "linkedin",
        "lead",
        "cold email",
        "crm",
        "sales",
    ),
    ValidCategory.ANALYTICS: (
        "analytics",
        "analyse",
        "dashboard",
        "kpi",
        "metrics",
        "data",
        "reporting",
    ),
    ValidCategory.CUSTOMER_SERVICE: (
        "support",
        "client",
        "helpdesk",
        "ticket",
        "chatbot",
        "zendesk",
        "intercom",
    ),
    ValidCategory.CODING: (
        "code",
        "coding",
        "developer",
        "api",
        "github",
        "copilot",
        "cursor",
    ),
    ValidCategory.IMAGE: (
        "image",
        "photo",
        "visuel",
        "midjourney",
        "dall-e",
        "design graphique",
    ),
    ValidCategory.VIDEO: (
        "video",
        "vidéo",
        "youtube",
        "montage",
        "clip",
    ),
    ValidCategory.WEBSITE: (
        "site web",
        "website",
        "landing",
        "wordpress",
        "webflow",
        "framer",
    ),
    ValidCategory.RESEARCH: (
        "research",
        "recherche",
        "veille",
        "market study",
        "étude",
    ),
}

# 2–3 actions métier par catégorie (utilisées en secours, pas comme chemin nominal)
_SUBTASK_TEMPLATES: dict[ValidCategory, tuple[str, ...]] = {
    ValidCategory.AUTOMATION: (
        "Relier les outils clés (déclencheur → actions → conditions) sans ressaisie manuelle",
        "Automatiser les étapes répétitives du parcours (notifications, sync, relances)",
    ),
    ValidCategory.SEO: (
        "Auditer pages et mots-clés prioritaires, corriger balises title/meta et structure Hn",
        "Optimiser pages money (accueil, collections, fiches) pour l'intention de recherche",
    ),
    ValidCategory.COPYWRITING: (
        "Rédiger ou réécrire les textes à fort impact conversion (hero, offre, CTA)",
        "Produire fiches produit / emails avec bénéfices clients et preuves sociales",
    ),
    ValidCategory.PROSPECTING: (
        "Définir ICP et listes cibles, enrichir contacts et séquencer l'outreach",
        "Qualifier les réponses et synchroniser le pipeline CRM",
    ),
    ValidCategory.ANALYTICS: (
        "Configurer le tracking des événements business (conversion, panier, churn)",
        "Construire un tableau de bord hebdo avec KPIs actionnables",
    ),
    ValidCategory.CUSTOMER_SERVICE: (
        "Centraliser tickets/chat et réponses types pour le support niveau 1",
        "Déployer FAQ / bot pour les questions récurrentes avant escalade humaine",
    ),
    ValidCategory.CODING: (
        "Implémenter intégrations API ou scripts de maintenance sur le stack existant",
        "Revue et durcissement des points sensibles (auth, webhooks, erreurs)",
    ),
    ValidCategory.IMAGE: (
        "Générer ou retoucher visuels produit / réseaux aux formats requis",
        "Harmoniser charte visuelle (couleurs, typographie, templates)",
    ),
    ValidCategory.VIDEO: (
        "Produire scripts et montages courts pour acquisition ou démo produit",
        "Adapter formats par canal (vertical, sous-titres, hooks 3s)",
    ),
    ValidCategory.WEBSITE: (
        "Structurer landing / site (sections, preuves, formulaires) orientée conversion",
        "Publier et connecter analytics + pixels sur le domaine",
    ),
    ValidCategory.RESEARCH: (
        "Synthétiser concurrence, pricing et messages du marché cible",
        "Extraire insights clients (avis, interviews) pour affiner l'offre",
    ),
}

_SECTOR_BOOST: dict[str, tuple[ValidCategory, ...]] = {
    "ecommerce": (ValidCategory.AUTOMATION, ValidCategory.COPYWRITING, ValidCategory.SEO),
    "saas": (ValidCategory.PROSPECTING, ValidCategory.COPYWRITING, ValidCategory.ANALYTICS),
    "agency": (ValidCategory.COPYWRITING, ValidCategory.AUTOMATION, ValidCategory.ANALYTICS),
}

_TOOL_TOKENS = re.compile(
    r"\b(airtable|notion|shopify|stripe|hubspot|salesforce|slack|google sheets?|"
    r"zapier|make|n8n|wordpress|webflow|mailchimp|brevo)\b",
    re.I,
)


def detect_categories_from_text(text: str) -> list[ValidCategory]:
    lower = text.lower()
    found: list[ValidCategory] = []
    for category, keywords in _KEYWORD_MAP.items():
        if any(kw in lower for kw in keywords):
            found.append(category)
    if not found:
        found = [ValidCategory.AUTOMATION]
    seen: set[ValidCategory] = set()
    ordered: list[ValidCategory] = []
    for c in found:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _ordered_categories(objective: str, sector: str) -> list[ValidCategory]:
    detected = detect_categories_from_text(f"{objective} {sector}")
    boost = _SECTOR_BOOST.get(sector.lower().strip(), ())
    merged: list[ValidCategory] = []
    seen: set[ValidCategory] = set()
    for c in (*boost, *detected):
        if c not in seen:
            seen.add(c)
            merged.append(c)
    return merged[:6]


def _actions_for_category(category: ValidCategory, objective: str) -> list[str]:
    templates = list(_SUBTASK_TEMPLATES.get(category, (f"Exécuter le volet {category.value}",)))
    lower = objective.lower()
    if category == ValidCategory.AUTOMATION and "shopify" in lower:
        templates = [
            "Synchroniser commandes, stocks et statuts clients entre Shopify et les outils satellites",
            "Automatiser relances panier abandonné et notifications post-achat",
            *templates,
        ]
    if category == ValidCategory.COPYWRITING and any(
        k in lower for k in ("shopify", "boutique", "e-commerce", "ecommerce")
    ):
        templates = [
            "Rédiger fiches produit orientées conversion (titre, bénéfices, objections, CTA)",
            *templates,
        ]
    return templates[:3]


def build_bulletproof_fallback(
    objective: str,
    sector: str,
    budget_max: int,
) -> AnalyzedQuery:
    """
    Plan structuré par catégorie — uniquement si RECO_ALLOW_HEURISTIC_FALLBACK=true.
    """
    categories = _ordered_categories(objective, sector)
    tasks: list[AtomicSubtask] = []
    task_counter = 0
    prev_id: str | None = None

    for cat in categories:
        for action in _actions_for_category(cat, objective):
            task_counter += 1
            tid = f"fb_t{task_counter}"
            depends = [prev_id] if prev_id else []
            tasks.append(
                AtomicSubtask(
                    id=tid,
                    action=action,
                    required_category=cat,
                    depends_on=depends,
                    can_be_automated=True,
                )
            )
            prev_id = tid

    domains_by_cat: dict[str, list[AtomicSubtask]] = {}
    for st in tasks:
        key = st.required_category.value
        domains_by_cat.setdefault(key, []).append(st)

    domains = [
        FunctionalDomain(
            name=cat.replace("_", " ").title(),
            priority=i + 1,
            subtasks=sts,
        )
        for i, (cat, sts) in enumerate(domains_by_cat.items())
    ]

    return AnalyzedQuery(
        original=objective,
        domains=domains,
        implicit_constraints=[
            "Analyse LLM indisponible — plan heuristique enrichi (qualité inférieure au LLM)",
        ],
        sector_context=sector,
        budget_max=budget_max,
    )


def extract_tool_tokens_from_text(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOOL_TOKENS.finditer(text)}
