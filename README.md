<h1 align="center">
  Pluto
</h1>

<p align="center">
  A proof-of-concept swiss-army knife for 
  managing High-Performance Computing clusters built with Ubuntu and Juju.
</p>

## Description

Pluto is proof-of-concept application for demonstrating the work that the 
High-Performance Computing (HPC) team at Canonical has accomplished over the past several months.
Pluto showcases the [__Charmed HPC__](https://ubuntu.com/hpc) project by automatically
bootstrapping a working cluster. The following services are deployed by Pluto to build the
cluster:

- SLURM + Munge -> Provides workload scheduling and resource management.
- GLAuth + SSSD -> Provides identity management service for users and groups.
- NFSv4 -> Provides shared filesystem.

After several minutes, you will have a fully-functional charmed micro-HPC cluster at your
fingertips! Take the cluster for a spin and see how Ubuntu can meet your HPC needs!

Note: Pluto is proof-of-concept application to set up a small, working Charmed HPC cluster
for personal experimentation. It __should not__ be used for production-level deployments.

## Usage

### Requirements

Your system needs to have the following requirements installed to use 
pluto to deploy a micro-HPC cluster:

- [snapd](https://snapcraft.io/docs/installing-snapd) 
- [juju >= 3.1](https://snapcraft.io/juju)

Also, you should have access to a 
[Juju supported cloud](https://juju.is/docs/olm/juju-supported-clouds) as well. Pluto only
supports machine charms, so Kubernetes-base clouds such as microk8s or Google GKE 
are not supported. If you are planning on using LXD as your cloud, see the
section [Appendix: Using LXD](#appendix-using-lxd) for extra steps before you bootstrap
the micro-HPC cluster.

### Setting up Juju

After installing snapd and juju, bootstrap a cloud controller using the following command:

```shell
juju bootstrap
```

You will be taken an interactive dialog to configure your cloud controller.
Please visit the [Juju documentation](https://juju.is/docs/olm/juju-supported-clouds) 
for specific information on how to bootstrap a Juju controller for your target cloud.

### Bootstrapping your micro-HPC cloud

Once the Juju controller for the cloud of you choice has been bootstrapped, use `snap`
to install pluto:

```shell
sudo snap install pluto 
```

Connect the snap interfaces needed by `pluto` to complete the installation.

```shell
sudo snap connect pluto:ssh-public-keys
sudo snap connect pluto:dot-local-share-juju
```

Now use the following command to bootstrap your HPC cluster:

```shell
pluto bootstrap test-cluster
```

In several minutes you will now have access to your very own HPC cluster! Have fun!

### Include identity management services
You can include identity management services in your deployment by passing the `--include-identity`
when you invoke the `bootstrap` command.

```shell
pluto bootstrap myhpccloud --include-identity
```

### Include VantageHPC integration
Add your HPC cluster to the VantageHPC platform by setting the `CLIENT_ID` and `CLIENT_SECRET`
environment variables and passing the `--include-vantage` flag to the `bootstrap` command.

```shell
CLIENT_ID=blah CLIENT_SECRET=blahblah pluto bootstrap myhpccloud --include-vantage
```


### Appendix: Using LXD

pluto will not initially work with LXD due to LXD containers being initially unable to mount
or export NFS shares. This has to do with LXD containers AppArmor configuration. To enable NFS
exporting/mounting, use the following commands to modify the default LXD profile on your system.
This needs to be done __before__ you bootstrap the HPC cluster with pluto:

```shell
lxc profile set default security.privileged true
lxc profile set default raw.apparmor 'mount fstype=nfs*, mount fstype=rpc_pipefs,'
```

Note: Given that you need to elevate the privileges of the LXD containers for the HPC
cluster to function, it is strongly recommended to use another cloud provider such as 
OpenStack or MAAS.

## Contributing

Pluto is just a proof-of-concept for deploying charmed HPC clusters, so it most likely
will not receive heavy feature development. However, if you notice any issues, feel free to open
a bug report!

## License

Pluto is free software, distributed under the GNU General Public License version 3. See
[LICENSE](./LICENSE) for more details.

