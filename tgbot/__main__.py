"""
Точка входа: `python -m tgbot [polling|serve]`.

polling — бот сам ходит за апдейтами (работает без публичного адреса);
serve   — поднимает HTTP-сервер с вебхуком и мини-аппом.
"""

import argparse
import asyncio
import logging

from .config import load_config
from .polling import run_polling


def main() -> None:
    parser = argparse.ArgumentParser(prog="tgbot")
    parser.add_argument("mode", nargs="?", default="polling", choices=["polling", "serve"])
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()

    if args.mode == "polling":
        asyncio.run(run_polling(config))
        return

    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
