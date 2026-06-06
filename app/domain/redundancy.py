"""Anti-redondance — aligné stackai/lib/agents/redundantGroups.ts"""

REDUNDANT_TOOL_GROUPS: list[list[str]] = [
    ["Lavender", "Outreach", "Lemlist", "Instantly", "Mailchimp", "Brevo", "Klaviyo", "Postscript"],
    ["Cursor", "GitHub Copilot", "Windsurf", "Codeium"],
    ["Ahrefs", "Semrush", "Moz"],
    ["Minea", "Sell The Trend", "Dropship.io"],
    ["Crisp", "Chatling", "Chatbase", "Webbotify", "Tidio", "Intercom", "Drift", "Landbot"],
    ["Freshdesk", "Zendesk", "Help Scout", "Zoho Desk", "Front"],
    ["Voiceflow", "Botpress", "ManyChat"],
]


def _name_in_group(name: str, group: list[str]) -> bool:
    lower = name.lower().strip()
    for token in group:
        t = token.lower()
        if lower == t or lower.startswith(t + " ") or t in lower:
            return True
    return False


def remove_redundant_by_groups[T](agents: list[T], name_getter=lambda a: getattr(a, "name", "")) -> list[T]:
    result = list(agents)
    for group in REDUNDANT_TOOL_GROUPS:
        found = [a for a in result if _name_in_group(name_getter(a), group)]
        if len(found) > 1:
            to_remove = found[1:]
            result = [a for a in result if a not in to_remove]
    return result
