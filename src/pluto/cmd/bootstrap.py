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
from zipfile import ZipFile

from craft_cli import BaseCommand, emit

from pluto.drivers import Cluster

glauth_cfg = """
[ldap]
  enabled = true
  listen = "0.0.0.0:363"

[ldaps]
  enabled = true
  listen = "0.0.0.0:636"
  cert = "glauth.crt"
  key = "glauth.key"

[backend]
  datastore = "config"
  baseDN = "dc=glauth,dc=com"
  nameformat = "cn"
  groupformat = "ou"
  anonymousdse = true

[behaviors]
  IgnoreCapabilities = false
  LimitFailedBinds = true
  NumberOfFailedBinds = 3
  PeriodOfFailedBinds = 10
  BlockFailedBindsFor = 60
  PruneSourceTableEvery = 600
  PruneSourcesOlderThan = 600

[[users]]
  name = "researcher"
  givenname="Researcher"
  sn="Science"
  mail = "researcher@ubuntu.com"
  uidnumber = 5002
  primarygroup = 5501
  loginShell = "/bin/bash"
  homeDir = "/home/researcher"
  passsha256 = "6478579e37aff45f013e14eeb30b3cc56c72ccdc310123bcdf53e0333e3f416a" # dogood
  passappsha256 = [
    "c32255dbf6fd6b64883ec8801f793bccfa2a860f2b1ae1315cd95cdac1338efa", # TestAppPw1
    "c9853d5f2599e90497e9f8cc671bd2022b0fb5d1bd7cfff92f079e8f8f02b8d3", # TestAppPw2
    "4939efa7c87095dacb5e7e8b8cfb3a660fa1f5edcc9108f6d7ec20ea4d6b3a88", # TestAppPw3
  ]

[[users]]
  name = "serviceuser"
  mail = "serviceuser@example.com"
  uidnumber = 5003
  primarygroup = 5502
  passsha256 = "652c7dc687d98c9889304ed2e408c74b611e86a40caa51c4b43f1dd5913c5cd0" # mysecret
    [[users.capabilities]]
    action = "search"
    object = "*"

[[groups]]
  name = "researchers"
  gidnumber = 5501

[[groups]]
  name = "svcaccts"
  gidnumber = 5502
"""


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
            cluster.deploy("mysql", channel="8.0/edge", num_units=1, base="ubuntu@22.04"),
            cluster.deploy(
                "mysql-router",
                application_name="slurmdbd-mysql-router",
                channel="dpe/edge",
                num_units=0,
                base="ubuntu@22.04",
            ),
            cluster.deploy("sssd", channel="edge", num_units=0, base="ubuntu@22.04"),
            cluster.deploy(
                "glauth",
                config={"ldap-search-base": "dc=glauth,dc=com", "tls": "true"},
                channel="edge",
                num_units=1,
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
            cluster.integrate("slurmd:juju-info", "sssd:juju-info"),
            cluster.integrate("slurmctld:juju-info", "sssd:juju-info"),
            cluster.integrate("nfs-server:juju-info", "sssd:juju-info"),
        )

        emit.progress("Provisioning identity management service")
        async with cluster.quick_fire():
            await cluster.wait(apps=["glauth"], status="active", timeout=1200)
        with tempfile.NamedTemporaryFile(suffix=".zip") as cfg:
            with ZipFile(cfg.name, "w") as cfg_zip:
                cfg_zip.writestr("microhpc.cfg", glauth_cfg)
            await cluster.attach_resource("glauth", {"config": cfg.name})
        for unit in cluster.units("glauth"):
            result = await unit.run_action(
                "set-confidential",
                **{
                    "ldap-password": "mysecret",
                    "ldap-default-bind-dn": "cn=serviceuser,ou=svcaccts,dc=glauth,dc=com",
                },
            )
            await result.wait()

        emit.progress("Integrating identity management service")
        await cluster.integrate("glauth:ldap-client", "sssd:ldap-client")

        emit.progress("Provisioning NFS server")
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

        emit.progress("Provisioning default user 'researcher'")
        async with cluster.quick_fire():
            await cluster.wait(apps=["sssd"], status="active", timeout=1200)
        for unit in cluster.units("sssd"):
            if await unit.is_leader_from_status():
                await unit.ssh("sudo mkdir -p /home/researcher")
                await unit.ssh("sudo chown researcher /home/researcher")


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
        emit.message("MicroHPC cluster deployed. Cluster will stabilize after several minutes.")
