'''
Photos Matrix File Download
'''
from typing import cast
import logging.config
import asyncio
import signal
import sys
import argparse
import yaml
from aiohttp import ClientSession
from mautrix.util.logging import TraceLogger
from .photos_client import PhotOsClient

#pylint: disable=global-statement, missing-function-docstring, broad-except, global-variable-not-assigned
loop = asyncio.get_event_loop()

commandline_parser = argparse.ArgumentParser(description="PhotOS Matrix client")
commandline_parser.add_argument("-c", "--config", type=str,
                                default="~/config.yaml",
                                required=True, metavar="<path>",
                                help="the path to your config file")

args = commandline_parser.parse_args()

PHOTOS_CLIENT = None
HTTP_CLIENT = None
CONFIG = None

with open(args.config, 'r', encoding='utf-8') as stream:
    CONFIG = yaml.load(stream, Loader=yaml.FullLoader)

logging.config.dictConfig(CONFIG["logging"])
logger = logging.getLogger(__name__)
TRACE_LOGGER = cast(TraceLogger, logger)

async def main():
    global HTTP_CLIENT
    HTTP_CLIENT = ClientSession(loop=loop)
    global PHOTOS_CLIENT

    async def try_connect() -> bool:
        try:
            global PHOTOS_CLIENT
            global TRACE_LOGGER
            global CONFIG
            await PHOTOS_CLIENT.initialize()
            await PHOTOS_CLIENT.start()
            return True
        except Exception as exception:
            TRACE_LOGGER.exception(exception)
            return False

    PHOTOS_CLIENT = PhotOsClient(CONFIG["matrix"], HTTP_CLIENT, TRACE_LOGGER)

    while not await try_connect():
        print('failure')
        await asyncio.sleep(5)

async def stop() -> None:
    logger.info('terminate client')
    if PHOTOS_CLIENT:
        await PHOTOS_CLIENT.stop()

    if HTTP_CLIENT:
        await HTTP_CLIENT.close()

try:
    logger.info("Starting PhotOS Matrix Client")
    loop.run_until_complete(main())
except Exception:
    logger.fatal("Failed to start plugin", exc_info=True)
    loop.run_until_complete(stop())
    loop.close()
    sys.exit(1)

signal.signal(signal.SIGINT, signal.default_int_handler)
signal.signal(signal.SIGTERM, signal.default_int_handler)

try:
    logger.info("Startup completed, running forever")
    loop.run_forever()
except KeyboardInterrupt:
    logger.info("Interrupt received, stopping")
    loop.run_until_complete(stop())
    loop.close()
    sys.exit(0)

except Exception:
    logger.fatal("Fatal error in PhotOS Matrix Client", exc_info=True)
    sys.exit(1)
#pylint: enable=global-statement, missing-function-docstring, broad-except, global-variable-not-assigned
