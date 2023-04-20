#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""pluto.

A swiss-army knife for managing HPC clusters built with Ubuntu.
"""

__version__ = "0.1.0"

import sys
import textwrap

from craft_cli import (
    ArgumentParsingError,
    CommandGroup,
    Dispatcher,
    EmitterMode,
    ProvideHelpException,
    emit,
)

from pluto.cmd import BootstrapCommand


def main() -> None:
    """Entry point for pluto program."""
    emit.init(EmitterMode.BRIEF, "pluto", f"Starting pluto version {__version__}")
    command_groups = [CommandGroup("Cluster Management", [BootstrapCommand])]

    try:
        dispatcher = Dispatcher(
            "pluto",
            command_groups,
            summary=textwrap.dedent(
                """
                Pluto is a swiss-army knife for managing HPC clusters built with Ubuntu.

                Together with Juju, pluto simplifies HPC cluster deployment and lifecycle
                operations, and enables collaboration between system administrators.

                See https://ubuntu.com/hpc for more information.
                """
            ),
        )
        dispatcher.pre_parse_args(sys.argv[1:])
        dispatcher.load_command(None)
        exit_code = dispatcher.run()
    except ArgumentParsingError as e:
        print(e, file=sys.stderr)
        emit.ended_ok()
        exit_code = 1
    except ProvideHelpException as e:
        print(e, file=sys.stderr)
        emit.ended_ok()
        exit_code = 0
    else:
        emit.ended_ok()
        if exit_code is None:
            exit_code = 0

    return exit_code
