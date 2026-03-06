"""Точка входа в приложение Telegram-бота."""

import logging

from bot.app import build_app, create_bot
from config import LONG_POLLING_TIMEOUT, POLLING_TIMEOUT


def main() -> None:
    """Инициализирует бота, регистрирует обработчики и запускает polling.

    Функция настраивает общий формат логирования, создаёт экземпляр бота,
    подключает обработчики команд/сообщений и запускает бесконечный цикл
    опроса Telegram API.
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
