"""Role -> capability mapping. Single source of truth for the UI, REST API and (later) MCP tools."""

ROLES: dict[str, str] = {
    "faculty": "Faculty",
    "technician": "Lab Technician",
    "incharge": "Venue In-charge",
    "oa": "Office Assistant / DEO",
    "hod": "HOD",
    "director": "Director - Infrastructure Management",
}

# Students have no login; these capabilities apply to everyone, including anonymous visitors.
PUBLIC_CAPABILITIES = frozenset({"view_venues", "check_availability", "use_assistant"})

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "faculty": frozenset({"book", "save_chat_history"}),
    "technician": frozenset({"update_equipment_own", "notified_of_events", "save_chat_history"}),
    "incharge": frozenset(
        {
            "book",
            "update_equipment_own",
            "edit_venue_own",
            "approve_own_venues",
            "notified_of_events",
            "reports_own",
            "save_chat_history",
        }
    ),
    "oa": frozenset({"upload_timetables", "upload_documents", "save_chat_history"}),
    "hod": frozenset(
        {
            "book",
            "approve_cse_venues",
            "approve_displacement",
            "upload_timetables",
            "upload_documents",
            "reports_cse",
            "save_chat_history",
        }
    ),
    "director": frozenset(
        {
            "book",
            "update_equipment_all",
            "edit_venue_all",
            "create_venue",
            "approve_all",
            "approve_displacement",
            "upload_timetables",
            "upload_documents",
            "reports_all",
            "manage_settings",
            "save_chat_history",
        }
    ),
}


def capabilities_for(role_keys: list[str] | None) -> set[str]:
    caps = set(PUBLIC_CAPABILITIES)
    for key in role_keys or []:
        caps |= ROLE_CAPABILITIES.get(key, frozenset())
    return caps


def has_capability(role_keys: list[str] | None, capability: str) -> bool:
    return capability in capabilities_for(role_keys)
