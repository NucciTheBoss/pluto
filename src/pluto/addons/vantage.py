#!/usr/bin/env python3
"""This module contains the vantagehpc addon provisioning methods."""
import asyncio
from typing import Dict

from pluto.drivers import Cluster


async def provision_vantage(cluster: Cluster, vantage_credentials: Dict[[str], [str]]) -> None:
    """Add the vantage services to the deployment."""
    jobbergate_charm_config: Dict[[str], [str]] = {
        "base-api-url": "https://apis.vantagehpc.io",
        "oidc-domain": "auth.vantagehpc.io/realms/vantage",
        "oidc-audience": "https://apis.vantagehpc.io",
        "slurmrestd-jwt-key-path": "/var/spool/slurmctld/jwt_hs256.key",
        "x-slurm-user-name": "ubuntu",
        "slurm-restd-version": "v0.0.39",
        "oidc-client-id": vantage_credentials["client_id"],
        "oidc-client-secret": vantage_credentials["client_secret"],
    }

    await asyncio.gather(
        cluster.deploy(
            "jobbergate-agent",
            config=jobbergate_charm_config,
            channel="edge",
            num_units=0,
            base="ubuntu@22.04",
        ),
    )
    await asyncio.gather(cluster.integrate("slurmrestd:juju-info", "jobbergate-agent:juju-info"))

    async with cluster.quick_fire():
        await cluster.wait(
            apps=["jobbergate-agent"], status="active", raise_on_error=False, timeout=1200
        )
