import logging

from bot.app import build_app, create_bot
from config import LONG_POLLING_TIMEOUT, POLLING_TIMEOUT


def main() -> None:
    """Запуск бота."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    bot = create_bot()
    build_app(bot)
    logging.getLogger(__name__).info('Бот запущен')
    bot.polling(none_stop=True, interval=0, timeout=POLLING_TIMEOUT,
                long_polling_timeout=LONG_POLLING_TIMEOUT)


if __name__ == '__main__':
    main()
