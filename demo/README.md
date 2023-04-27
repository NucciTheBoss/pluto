# Showcasing Charmed HPC

## Before the demo setup

1. Ensure that Juju 3.1/stable or greater is installed on your machine.

```shell
sudo snap install juju --channel 3.1/stable
```

2. Bootstrap a Juju controller. DO NOT USE LXD UNLESS ABSOLUTELY NECESSARY!!

```shell
juju bootstrap  #=> Walkthrough interactive terminal prompt
```

3. Install pluto snap package and ensure that all interfaces are connected

```shell
sudo snap connect pluto:ssh-public-keys snapd
sudo snap connect pluto:dot-local-share-juju snapd
sudo snap connect pluto:juju-bin juju:juju-bin
```

## During demo

1. Showcase pluto bootstrapping cluster.

```shell
pluto bootstrap
```

2. ssh into slurmctld/0 and log in as user _researcher_

```shell
juju ssh slurmctld/0
sudo -i -u researcher
```

3. Showcase dataset and Fortran file we have for processing data

```shell
less distro_name_dataset.csv
less hpsee.f90
```

4. Install gfortran and compile hpsee

```shell
sudo apt install gfortran
gfortran -o hpsee hpsee.f90
```

5. Showcase job file we will use to run hpsee binary to predict the Ubuntu release name

```shell
less guess-the-name.submit
```

6. Submit job

```shell
sbatch guess-the-name.submit
```

7. Show results

```shell
less *.stdout.log  #=> Log file name will vary based on deployment

# Outside slurmctld/0
juju scp slurmctld/0:outputdir/mantic-minotaur.jpeg mantic-minotaur.jpeg
display mantic-minotaur.jpeg  #=> Also recommend double-clicking from file explorer.
```
