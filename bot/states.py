"""Хранилище состояний пользовательских диалогов бота."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserState:
    """Описывает текущее состояние диалога конкретного пользователя.

    Attributes:
        kind: Тип состояния (`awaiting_time`, `pending_question`, `manual`,
            `edit`).
        step: Текущий шаг внутри сценария выбранного состояния.
        data: Дополнительный контекст сценария в формате словаря.
    """

    kind: str
    step: str
    data: dict[str, Any] = field(default_factory=dict)


class StateStore:
    """Предоставляет in-memory CRUD для состояний пользователей Telegram."""

    def __init__(self) -> None:
        """Создаёт пустое хранилище состояний по `user_id`."""
        self._states: dict[int, UserState] = {}

    def get(self, user_id: int) -> UserState | None:
        """Возвращает текущее состояние пользователя.

        Args:
            user_id: Идентификатор пользователя Telegram.

        Returns:
            UserState | None: Найденное состояние или `None`, если состояние
            отсутствует.
        """
        return self._states.get(user_id)

    def set(self, user_id: int, state: UserState) -> None:
        """Сохраняет состояние пользователя.

        Args:
            user_id: Идентификатор пользователя Telegram.
            state: Подготовленное состояние диалога.
        """
        self._states[user_id] = state

    def clear(self, user_id: int) -> None:
        """Удаляет состояние пользователя, если оно существует.

        Args:
            user_id: Идентификатор пользователя Telegram.
        """
        self._states.pop(user_id, None)
