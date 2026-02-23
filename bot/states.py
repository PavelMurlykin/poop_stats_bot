from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class UserState:
    """
    Инкапсулирует сущность `UserState` в предметной области.

    Класс объединяет связанные данные и поведение для работы модуля.
    """
    kind: str   # awaiting_time | pending_question | manual | edit
    step: str
    data: Dict[str, Any] = field(default_factory=dict)


class StateStore:
    """
    Инкапсулирует сущность `StateStore` в предметной области.

    Класс объединяет связанные данные и поведение для работы модуля.
    """

    def __init__(self) -> None:
        """
        Выполняет операцию `__init__` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            self: Ссылка на текущий экземпляр класса.

        Returns:
            Ноне: Возвращаемое значение отсутствует.
        """
        self._states: Dict[int, UserState] = {}

    def get(self, user_id: int) -> Optional[UserState]:
        """
        Выполняет операцию `get` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            self: Ссылка на текущий экземпляр класса.
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            Optional[UserState]: Результат выполнения функции.
        """
        return self._states.get(user_id)

    def set(self, user_id: int, state: UserState) -> None:
        """
        Выполняет операцию `set` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            self: Ссылка на текущий экземпляр класса.
            user_id: Идентификатор пользователя в Telegram.
            state: Параметр `state` для текущего шага обработки.

        Returns:
            Ноне: Возвращаемое значение отсутствует.
        """
        self._states[user_id] = state

    def clear(self, user_id: int) -> None:
        """
        Выполняет операцию `clear` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            self: Ссылка на текущий экземпляр класса.
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            Ноне: Возвращаемое значение отсутствует.
        """
        self._states.pop(user_id, None)
