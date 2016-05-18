from __future__ import (absolute_import, print_function, division)

from itertools import repeat
import sys
import argparse
import os
import pytoml as toml

from . import cli
from . import proxyswitch
from . import say
from . import version
from libmproxy.main import mitmdump


def main():
    parser = argparse.ArgumentParser(prog = "mastermind",
                                     description = "Man in the middle testing tool")
    parser.add_argument("--version",
                        action="version",
                        version="%(prog)s" + " " + version.VERSION)

    driver = parser.add_argument_group("Driver")
    single = parser.add_argument_group("Single")
    script = parser.add_argument_group("Script")

    driver.add_argument("--with-driver",
                        action = "store_true",
                        help = "Activates the driver")
    driver.add_argument("--source-dir",
                        metavar = "DIR",
                        help = "An absolute path used as a source directory to lookup for mock rules")

    driver.add_argument("--config",
                        metavar = "CONFIG_FILE",
                        help = "A valid config file. See https://github.com/ustwo/mastermind/tree/master/docs/config.md")

    single.add_argument("--response-body",
                        metavar = "FILEPATH",
                        help = "A file containing the mocked response body")
    single.add_argument("--url",
                        metavar = "URL",
                        help = "A URL to mock its response")

    script.add_argument("--script",
                        metavar = "FILEPATH",
                        help = '''A mitmproxy Python script filepath.
                                  When passed, --response-body and --url are ignored''')

    parser.add_argument("--port",
                        help = "Default port 8080")
    parser.add_argument("--host",
                        help = "Default host 0.0.0.0")
    parser.add_argument("--without-proxy-settings",
                        action="store_true",
                        help="Skips changing the OS proxy settings")


    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument("--quiet",
                                 action="store_true",
                                 help="Makes Mastermind quiet")

    verbosity_group.add_argument("-v", "--verbose",
                                 action="count",
                                 help="Makes Mastermind verbose")

    args, extra_arguments = parser.parse_known_args()
    mitm_args = ["--host"]

    config = {"core": {"verbose": 2,
                       "host": "0.0.0.0",
                       "port": 8080},
              "driver": {},
              "mitm": {},
              "os": {"proxy-settings": True}}

    if args.config:
        try:
            with open(args.config) as config_file:
                data = toml.loads(config_file.read())
                if "os" in data:
                    config["os"].update(data["os"])
                if "core" in data:
                    config["core"].update(data["core"])
        except toml.core.TomlError as err:
            parser.error("Errors found in the config file:\n\n", err)

    config = cli.merge(config, args)

    if "source-dir" in config["core"]:
        cli.check_driver_mode(config, parser)

        storage_dir = os.path.expanduser("~/.mastermind/{}".format(os.getcwd().split("/")[-1]))
        config["core"]["storage-dir"] = storage_dir

        if not os.path.isdir(storage_dir):
            os.makedirs(storage_dir)

        script_path_template = "{}/scripts/flasked.py {} {} {} {} {}"
        script_path = os.path.dirname(os.path.realpath(__file__))
        if getattr( sys, 'frozen', False ):
            script_path = sys._MEIPASS

        mitm_args = ['--script',
                     script_path_template.format(script_path,
                                                 config["core"]["source-dir"],
                                                 config["os"]["proxy-settings"],
                                                 config["core"]["port"],
                                                 config["core"]["host"],
                                                 config["core"]["storage-dir"])]
    elif "script" in config["core"]:
        cli.check_script_mode(parser, config)

        mitm_args.append('--script')
        mitm_args.append(config["core"]["script"])

    elif ("response-body" in config["core"]) and ("url" in config["core"]):
        script_path_template = "{}/scripts/simple.py {} {} {} {} {}"
        script_path = os.path.dirname(os.path.realpath(__file__))

        if getattr(sys, 'frozen', False):
            script_path = sys._MEIPASS

        mitm_args = ['--script',
                     script_path_template.format(script_path,
                                                 config["core"]["url"],
                                                 config["core"]["response-body"],
                                                 config["os"]["proxy-settings"],
                                                 config["core"]["port"],
                                                 config["core"]["host"])]
    else:
        parser.print_help()
        parser.exit(1, "\n\nThe arguments used don't match any of the possible modes. Please check the help above\n")


    say.level(config["core"]["verbose"])

    if config["core"]["verbose"] <= 3:
        mitm_args.append("--quiet")

    if config["core"]["verbose"] > 3:
        mitm_args + list(repeat("-v", config["core"]["verbose"] - 3))

    mitm_args = mitm_args + extra_arguments
    mitm_args = mitm_args + ["--port", str(config["core"]["port"]),
                             "--bind-address", config["core"]["host"]]

    try:
        mitmdump(mitm_args)
    except:
        if config["os"]["proxy-settings"]:
            proxyswitch.disable()
