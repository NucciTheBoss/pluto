#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Bootstrap a new HPC cluster.

`pluto bootstrap ...`
"""

import argparse
import asyncio
import pathlib
import tempfile
import textwrap
from typing import Optional

from craft_cli import BaseCommand, emit

from pluto.drivers import Cluster


async def _bootstrap(name: str) -> None:
    """Bootstrap a new HPC cluster using Juju.

    Args:
        name: Name to use for the new HPC cluster.
    """
    async with Cluster(name) as cluster:
        emit.progress("Deploying HPC services")
        await asyncio.gather(
            cluster.deploy("slurmctld", channel="edge", num_units=1, base="ubuntu@22.04"),
            cluster.deploy("slurmd", channel="edge", num_units=3, base="ubuntu@22.04"),
            cluster.deploy("slurmdbd", channel="edge", num_units=1, base="ubuntu@22.04"),
            cluster.deploy("slurmrestd", channel="edge", num_units=1, base="ubuntu@22.04"),
            cluster.deploy("mysql", channel="edge", num_units=1, base="ubuntu@22.04"),
            cluster.deploy(
                "mysql-router",
                application_name="slurmdbd-mysql-router",
                channel="edge",
                num_units=0,
                base="ubuntu@22.04",
            ),
            cluster.deploy(
                "nfs-client",
                application_name="home",
                config={"mountpoint": "/home"},
                channel="edge",
                num_units=0,
                base="ubuntu@22.04",
            ),
            cluster.deploy(
                "nfs-server-proxy",
                application_name="home-nfs-proxy",
                channel="edge",
                num_units=1,
                base="ubuntu@22.04",
            ),
            cluster.deploy(
                "ubuntu", application_name="nfs-server", num_units=1, base="ubuntu@22.04"
            ),
        )

        emit.progress("Integrating deployed HPC services")
        await asyncio.gather(
            cluster.integrate("slurmd:slurmd", "slurmctld:slurmd"),
            cluster.integrate("slurmrestd:slurmrestd", "slurmctld:slurmrestd"),
            cluster.integrate("slurmdbd:slurmdbd", "slurmctld:slurmdbd"),
            cluster.integrate("slurmdbd-mysql-router:backend-database", "mysql:database"),
            cluster.integrate("slurmdbd:database", "slurmdbd-mysql-router:database"),
            cluster.integrate("slurmd:juju-info", "home:juju-info"),
            cluster.integrate("slurmctld:juju-info", "home:juju-info"),
        )

        emit.progress("Waiting for NFS server")
        async with cluster.quick_fire():
            await cluster.wait(apps=["nfs-server"], status="active", timeout=1000)

        emit.progress("Provisioning NFS server")
        for unit in cluster.units("nfs-server"):
            await unit.ssh("sudo apt install nfs-kernel-server")
            with tempfile.NamedTemporaryFile() as exports:
                pathlib.Path(exports.name).write_text(
                    textwrap.dedent(
                        """
                        /srv     *(ro,sync,subtree_check)
                        /home    *(rw,sync,no_subtree_check)
                        """
                    ).strip("\n")
                )
                await unit.scp_to(exports.name, "~/exports")
            await unit.ssh("sudo mv ~/exports /etc/exports")
            await unit.ssh("sudo exportfs -a")
            await unit.ssh("sudo systemctl restart nfs-kernel-server")
            endpoint = f"nfs://{await unit.get_public_address()}/home"

        emit.progress("Integrating cluster filesystem")
        await cluster.get_app("home-nfs-proxy").set_config({"endpoint": endpoint})
        await cluster.integrate("home-nfs-proxy:nfs-share", "home:nfs-share")


class BootstrapCommand(BaseCommand):
    """Bootstrap a new HPC cluster."""

    name = "bootstrap"
    help_msg = "Bootstrap a new HPC cluster."
    overview = textwrap.dedent(
        """
        Bootstrap a new HPC cluster.

        A Juju controller needs to be initialized before
        pluto can bootstrap a new HPC cluster or `bootstrap` will fail.

        The command will return after the relevant HPC nodes have been deployed.
        """
    )

    def run(self, parsed_args: argparse.Namespace) -> Optional[int]:
        """Bootstrap new HPC cluster."""
        emit.message("Deploying MicroHPC cluster. This will take several minutes...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_bootstrap("microhpc"))
        emit.message("MicroHPC cluster deployed. Cluster will stabilize after several minutes")
