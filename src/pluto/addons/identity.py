#!/usr/bin/env python3
"""This module contains the identity provisioning methods."""
import asyncio
import tempfile
from typing import Dict, Optional
from zipfile import ZipFile

from craft_cli import emit

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


async def provision_identity(
    cluster: Cluster, control_constraint: Optional[Dict[str, str]] = None
) -> None:
    """Add the identity services to the deployment."""
    await asyncio.gather(
        cluster.deploy("sssd", channel="edge", num_units=0, base="ubuntu@22.04"),
        cluster.deploy(
            "glauth",
            config={"ldap-search-base": "dc=glauth,dc=com", "tls": "true"},
            channel="edge",
            num_units=1,
            base="ubuntu@22.04",
            constraints=control_constraint,
        ),
    )
    await asyncio.gather(
        cluster.integrate("slurmd:juju-info", "sssd:juju-info"),
        cluster.integrate("slurmctld:juju-info", "sssd:juju-info"),
        cluster.integrate("nfs-server:juju-info", "sssd:juju-info"),
    )
    # Add custom configuration for glauth.
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

    emit.progress("Integrating identity management service...")
    await cluster.integrate("glauth:ldap-client", "sssd:ldap-client")

    emit.progress("Provisioning default user 'researcher'...")
    async with cluster.quick_fire():
        await cluster.wait(apps=["sssd"], status="active", raise_on_error=False, timeout=1200)
    for unit in cluster.units("nfs-server"):
        await unit.ssh("sudo mkdir -p /home/researcher")
        await unit.ssh("sudo chown -R researcher /home/researcher")
