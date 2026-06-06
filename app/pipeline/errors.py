"""Erreurs pipeline reco — qualité produit / disponibilité LLM."""


class RecoPipelineError(RuntimeError):
    """Erreur métier du moteur de recommandation."""


class QueryAnalyzerUnavailableError(RecoPipelineError):
    """Analyse LLM impossible après toute la chaîne fournisseurs (mode strict)."""
