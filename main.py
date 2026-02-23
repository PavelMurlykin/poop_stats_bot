import logging

from bot.app import build_app, create_bot
from config import LONG_POLLING_TIMEOUT, POLLING_TIMEOUT


def main() -> None:
    """
    Выполняет операцию `main` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    bot = create_bot()
    build_app(bot)
    logging.getLogger(__name__).info('Бот запущен')
    bot.infinity_polling(
        timeout=POLLING_TIMEOUT,
        long_polling_timeout=LONG_POLLING_TIMEOUT,
        logger_level=logging.INFO,
    )


if __name__ == '__main__':
    main()
