conversation_store: dict[str, list[dict]] = {}


def load_messages(session_id: str) -> list[dict]:
    return conversation_store.setdefault(session_id, [])


def append_message(session_id: str, role: str, content: str) -> list[dict]:
    history = conversation_store.setdefault(session_id, [])
    history.append({"role": role, "content": content})
    return history
