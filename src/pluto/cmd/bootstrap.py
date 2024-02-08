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
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request

from craft_cli import BaseCommand, emit

from pluto.addons.identity import provision_identity
from pluto.drivers import Cluster


def _parse_constraints(constraints: str) -> Dict[str, Any]:
    """Parse Juju constraints and return as dict.

    Args:
        constraints: Juju constraints line to parse.

    Yields:
        Parsed constraint values.
    """
    for constraint in constraints.split(","):
        key, value = constraint.split("=")
        yield key.replace("-", "_"), value


async def _bootstrap(
    name: str,
    num_compute: int,
    include_identity: bool,
    compute_constraint: Optional[Dict[str, str]] = None,
    control_constraint: Optional[Dict[str, str]] = None,
) -> None:
    """Bootstrap a new HPC cluster using Juju.

    Args:
        name: Name to use for the new HPC cluster.
        num_compute: Number of compute nodes to deploy.
        include_identity: Whether or not to include identity services.
        compute_constraint: Constraints to apply to compute plane nodes.
        control_constraint: Constraints to apply to control plane nodes.
    """
    async with Cluster(name) as cluster:
        emit.progress("Deploying HPC services...")
        with tempfile.TemporaryDirectory() as tmpdir:
            nhc = Path(tmpdir) / "lbnl-nhc-1.4.3.tar.gz"
            request.urlretrieve(
                f"https://github.com/mej/nhc/releases/download/1.4.3/{nhc.name}", nhc
            )
            await asyncio.gather(
                cluster.deploy(
                    "slurmctld",
                    channel="edge",
                    num_units=1,
                    base="ubuntu@22.04",
                    constraints=control_constraint,
                ),
                cluster.deploy(
                    "slurmd",
                    channel="edge",
                    num_units=num_compute,
                    base="ubuntu@22.04",
                    constraints=compute_constraint,
                    resources={"nhc": nhc},
                ),
                cluster.deploy(
                    "slurmdbd",
                    channel="edge",
                    num_units=1,
                    base="ubuntu@22.04",
                    constraints=control_constraint,
                ),
                cluster.deploy(
                    "slurmrestd",
                    channel="edge",
                    num_units=1,
                    base="ubuntu@22.04",
                    constraints=control_constraint,
                ),
                cluster.deploy(
                    "mysql",
                    channel="8.0/edge",
                    num_units=1,
                    base="ubuntu@22.04",
                    constraints=control_constraint,
                ),
                cluster.deploy(
                    "mysql-router",
                    application_name="slurmdbd-mysql-router",
                    channel="dpe/edge",
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
                    constraints=control_constraint,
                ),
                cluster.deploy(
                    "ubuntu",
                    application_name="nfs-server",
                    num_units=1,
                    base="ubuntu@22.04",
                    constraints=control_constraint,
                ),
            )

        emit.progress("Integrating deployed HPC services...")
        await asyncio.gather(
            cluster.integrate("slurmd:slurmd", "slurmctld:slurmd"),
            cluster.integrate("slurmrestd:slurmrestd", "slurmctld:slurmrestd"),
            cluster.integrate("slurmdbd:slurmdbd", "slurmctld:slurmdbd"),
            cluster.integrate("slurmdbd-mysql-router:backend-database", "mysql:database"),
            cluster.integrate("slurmdbd:database", "slurmdbd-mysql-router:database"),
            cluster.integrate("slurmd:juju-info", "home:juju-info"),
            cluster.integrate("slurmctld:juju-info", "home:juju-info"),
        )

        emit.progress("Provisioning NFS server...")
        async with cluster.quick_fire():
            await cluster.wait(apps=["nfs-server"], status="active", timeout=1200)
        for unit in cluster.units("nfs-server"):
            await unit.ssh("sudo apt -y install nfs-kernel-server")
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

        if include_identity:
            emit.progress("Provisioning identity services...")
            await provision_identity(cluster, control_constraint)

        emit.progress("Starting compute nodes...")
        for unit in cluster.units("slurmd"):
            await unit.run_action("node-configured")


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

    def fill_parser(self, parser: argparse.ArgumentParser) -> None:
        """Define arguments and flags to pass to bootstrap."""
        parser.add_argument("name", type=str, help="Name for deployed cluster.")
        parser.add_argument(
            "--compute", type=int, default=1, help="Number of compute nodes to bootstrap."
        )
        parser.add_argument(
            "--compute-plane-constraints",
            type=str,
            required=False,
            help="Constraints to pass to compute nodes.",
        )
        parser.add_argument(
            "--control-plane-constraints",
            type=str,
            required=False,
            help="Constraints to pass to control plane nodes.",
        )
        parser.add_argument(
            "--include-identity",
            action="store_true",
            help="Include glauth and sssd identity management services.",
        )

    def run(self, parsed_args: argparse.Namespace) -> Optional[int]:
        """Bootstrap new HPC cluster."""
        compute_constraints = None
        control_constraints = None
        if c := parsed_args.compute_plane_constraints:
            compute_constraints = dict(_parse_constraints(c))
        if c := parsed_args.control_plane_constraints:
            control_constraints = dict(_parse_constraints(c))

        name = parsed_args.name
        num_compute = parsed_args.compute
        include_identity = parsed_args.include_identity
        emit.message(f"Deploying cluster {name}. This will take several minutes...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            _bootstrap(
                name, num_compute, include_identity, compute_constraints, control_constraints
            )
        )
        emit.message(f"{name} cluster deployed. Cluster will stabilize soon...")
