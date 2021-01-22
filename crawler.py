#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import argparse
import os
import sys
import warnings

try:
    # Python 3.7 and newer, fast reentrant implementation
    # without task tracking (not needed for that when logging)
    from queue import SimpleQueue as Queue
except ImportError:
    from queue import Queue
from logging.handlers import QueueHandler, QueueListener

from async_lru import alru_cache
from logging import (
    Formatter,
    FileHandler,
    DEBUG,
    INFO,
    StreamHandler,
    getLogger,
)

warnings.filterwarnings("ignore")

BLACKLIST = [
    '/redfish/v1/jsonschemas',
    '/redfish/v1/managers/idrac.embedded.1/logservices/',
    '/redfish/v1/managers/idrac.embedded.1/logservices/lclog',
]


async def crawler_factory(_host, _username, _password, _logger, _loop=None):
    crawler = Crawler(_host, _username, _password, _logger, _loop)
    await crawler.init()
    return crawler


class CrawlerException(Exception):
    pass


class Node:
    def __init__(self, endpoint, data=None, directory=None, childs=None):
        self.endpoint = endpoint
        self.data = data
        self.directory = directory
        self.childs = childs


class Crawler:
    def __init__(self, _host, _username, _password, _logger, _loop=None):
        self.host = _host
        self.username = _username
        self.password = _password
        self.host_uri = "https://%s" % _host
        self.redfish_uri = "/redfish/v1"
        self.root_uri = "%s%s" % (self.host_uri, self.redfish_uri)
        self.logger = _logger
        self.semaphore = asyncio.Semaphore(20)
        self.root_dir = None
        if not _loop:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = _loop

    async def init(self):
        await self.validate_credentials()
        self.root_dir = self.host.split(".")[0]
        if not os.path.exists(self.root_dir):
            os.mkdir(self.root_dir)

    @alru_cache(maxsize=64)
    async def get_request(self, uri):
        try:
            async with self.semaphore:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        uri,
                        auth=aiohttp.BasicAuth(self.username, self.password),
                        verify_ssl=False,
                        timeout=60,
                    ) as _response:
                        await _response.read()
        except (Exception, TimeoutError) as ex:
            self.logger.debug(ex)
            self.logger.error("Failed to communicate with server.")
            raise CrawlerException
        return _response

    async def validate_credentials(self):
        response = await self.get_request(self.root_uri + "/Systems")

        if response.status == 401:
            self.logger.error(
                f"Failed to authenticate. Verify your credentials for {self.host}"
            )
            raise CrawlerException

        if response.status not in [200, 201]:
            self.logger.error(f"Failed to communicate with {self.host}")
            raise CrawlerException

    async def get_data(self, uri):
        response = await self.get_request(self.host_uri + uri)

        if response.status == 403:
            endpoint = uri.split("/")[-1]
            self.logger.warning(
                f"Can't access {endpoint}. Obtain an appropriate license then try again. SKIPPING"
            )
            return None

        if response.status not in [200, 201]:
            self.logger.error(f"Failed to communicate with {self.host}")
            raise CrawlerException

        raw = await response.text("utf-8", "ignore")
        data = json.loads(raw.strip())

        return data

    async def get_node(self, root, value):
        endpoint = value.get("@odata.id")
        if endpoint:
            if endpoint.lower() in BLACKLIST:
                return None
            directory_suffix = endpoint.split("/")[-1]
            directory = os.path.join(root.directory, directory_suffix)
            if not os.path.exists(directory):
                os.mkdir(directory)
            node_data = await self.get_data(endpoint)
            node = Node(endpoint=endpoint, data=node_data, directory=directory)
            if node_data:
                with open(os.path.join(directory, "out.json"), "w") as output:
                    output.write(json.dumps(node_data, indent=2))
                node.data = node_data
            return node
        return None

    async def get_childs(self, root):
        nodes = []
        if root.data:
            for key, value in root.data.items():
                if type(value) == dict:
                    node = await self.get_node(root, value)
                    if node:
                        await self.get_childs(node)
                        nodes.append(node)
                elif type(value) == list:
                    if key.lower() == "members":
                        for member in value:
                            node = await self.get_node(root, member)
                            if node:
                                await self.get_childs(node)
                                nodes.append(node)

        root.childs = nodes

    async def crawl(self):
        data = await self.get_data(self.redfish_uri)

        root = Node(
            endpoint=data.get("@odata.id"),
            data=data,
            directory=self.root_dir
        )
        await self.get_childs(root)


async def execute_crawler(_host, _args, logger):
    _username = _args["u"]
    _password = _args["p"]

    try:
        crawler = await crawler_factory(
            _host=_host,
            _username=_username,
            _password=_password,
            _logger=logger,
        )
        await crawler.crawl()
    except CrawlerException as ex:
        logger.debug(ex)
        logger.error("There was something wrong executing Crawler")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-H", help="iDRAC host address")
    parser.add_argument("-u", help="iDRAC username", required=True)
    parser.add_argument("-p", help="iDRAC password", required=True)
    parser.add_argument(
        "-l", "--log", help="Optional argument for logging results to a file"
    )
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    _args = vars(parser.parse_args(argv))

    log_level = DEBUG if _args["verbose"] else INFO

    host = _args["H"]

    FMT = "- %(levelname)-8s - %(message)s"
    FILEFMT = "%(asctime)-12s: %(levelname)-8s - %(message)s"

    _queue = Queue()
    _stream_handler = StreamHandler()
    _stream_handler.setFormatter(Formatter(FMT))
    _queue_listener = QueueListener(_queue, _stream_handler)
    _logger = getLogger(__name__)
    _queue_handler = QueueHandler(_queue)
    _logger.addHandler(_queue_handler)
    _logger.setLevel(log_level)

    _queue_listener.start()

    if _args["log"]:
        file_handler = FileHandler(_args["log"])
        file_handler.setFormatter(Formatter(FILEFMT))
        file_handler.setLevel(log_level)
        _queue_listener.handlers = _queue_listener.handlers + (file_handler,)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            execute_crawler(host, _args, _logger)
        )
    except KeyboardInterrupt:
        _logger.warning("Crawler terminated")
    except CrawlerException as ex:
        _logger.warning("There was something wrong executing Crawler")
        _logger.debug(ex)
    _queue_listener.stop()


if __name__ == "__main__":
    sys.exit(main())
