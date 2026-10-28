import os
from aiohttp import web
from .app import create_app
from .config import Config


def main():
    os.umask(0o077)
    config = Config.from_env()
    web.run_app(
        create_app(config),
        host=config.host,
        port=config.port,
        access_log=None,
        print=lambda _: print(f"LightPost: http://{config.host}:{config.port}"),
    )


if __name__ == "__main__":
    main()
