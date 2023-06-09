# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Juju driver for pluto."""

import asyncio
import contextlib
import os
from collections import namedtuple
from typing import Any, Dict, List, Optional, Union

from juju.application import Application
from juju.controller import Controller
from juju.model import Model
from juju.unit import Unit


class ClusterDriverError(Exception):
    """Raise if cluster driver encounters an error."""

    @property
    def name(self) -> str:
        """Get a string representation of the error plus class name."""
        return f"<{type(self).__module__}.{type(self).__name__}>"

    @property
    def message(self) -> str:
        """Return the message passed as an argument."""
        return self.args[0]

    def __repr__(self) -> str:
        """String representation of the error."""
        return f"<{type(self).__module__}.{type(self).__name__} {self.args}>"


Result = namedtuple("Result", ["exit_code", "stdout", "stderr"])


async def _juju(
    *cmd: str, cwd: Optional[Union[str, os.PathLike]] = None, check: bool = False
) -> Result:
    """Asynchronously execute a Juju command.

    Args:
        *cmd: Juju command to execute.
        cwd: Directory to execute Juju command from. Default: None.
        check: Check if Juju command succeeded. Default: False.
    """
    proc = await asyncio.create_subprocess_exec(
        *(["juju"] + [str(c) for c in cmd]),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd or "."),
    )
    _stdout, _stderr = await proc.communicate()
    stdout, stderr = _stdout.decode("utf8"), _stderr.decode("utf8")
    if check and proc.returncode != 0:
        raise ClusterDriverError(f"Juju command {list(cmd)} failed. Reason:\n{(stderr or stdout)}")

    return Result(proc.returncode, stdout, stderr)


class Cluster:
    """Control an HPC cluster using Juju from pluto."""

    def __init__(self, cluster: str) -> None:
        self._name = cluster
        self._controller = Controller()
        self._model = Model()

        # Alias Model methods to Cluster object.
        self.deploy = self._model.deploy
        self.integrate = self._model.integrate
        self.wait = self._model.wait_for_idle

    async def __aenter__(self) -> "Cluster":
        """Get instance of Cluster for controlling Juju."""
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Disconnect from Juju model and controller."""
        await self.close()

    async def connect(self) -> None:
        """Connect to HPC cluster."""
        await self._controller.connect()
        if not await self.exists():
            await self._controller.add_model(self.name)
        await self._model.connect(self.name)

    async def close(self) -> None:
        """Close connection to HPC cluster."""
        await self._model.disconnect()
        await self._controller.disconnect()

    @contextlib.asynccontextmanager
    async def quick_fire(self, interval: str = "10s") -> None:
        """Increase the rate of fire for update-status events.

        Args:
            interval: Interval to set update-status firing rate.
        """
        if not self.connected():
            raise ClusterDriverError(f"Connection to {self.name} not established")

        old_interval = (await self._model.get_config())["update-status-hook-interval"]
        await self._model.set_config({"update-status-hook-interval": interval})
        yield
        await self._model.set_config({"update-status-hook-interval": old_interval})

    @property
    def name(self) -> str:
        """Get name of HPC cluster."""
        return self._name

    def connected(self) -> bool:
        """Determine if pluto is connected to the HPC cluster."""
        return True if self._model.is_connected() and self._controller.is_connected() else False

    async def exists(self) -> bool:
        """Determine if cluster exists or not."""
        models = await self._controller.list_models()
        return True if self.name in models else False

    def units(self, application_name: Optional[str]) -> List[Unit]:
        """Get units within a particular HPC application.

        Args:
            application_name:
                Application to get units from. If omitted,
                get all units in the HPC cluster.
        """
        if application_name:
            return self._model.applications[application_name].units
        return list(self._model.units.values())

    def get_app(self, application_name: str) -> Application:
        """Get application with cluster model.

        Args:
            application_name: Name application to retrieve.
        """
        return self._model.applications[application_name]

    async def attach_resource(
        self, application_name: str, resources: Dict[str, os.PathLike]
    ) -> None:
        """Attach resource to deployed application.

        Args:
            application_name: Application to upload resource to.
            resources: Resources to attach to application.
        """
        for k, v in resources.items():
            await _juju("attach-resource", application_name, f"{k}={v}")
