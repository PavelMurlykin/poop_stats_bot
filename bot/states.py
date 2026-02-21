from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class UserState:
    kind: str   # awaiting_time | pending_question | manual | edit
    step: str
    data: Dict[str, Any] = field(default_factory=dict)


class StateStore:
    def __init__(self) -> None:
        self._states: Dict[int, UserState] = {}

    def get(self, user_id: int) -> Optional[UserState]:
        return self._states.get(user_id)

    def set(self, user_id: int, state: UserState) -> None:
        self._states[user_id] = state

    def clear(self, user_id: int) -> None:
        self._states.pop(user_id, None)
