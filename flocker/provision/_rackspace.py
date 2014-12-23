# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Rackspace provisioner.
"""

from ._libcloud import monkeypatch, LibcloudProvisioner
from ._install import provision, run, task_disable_firewall


def provision_rackspace(node, package_source, distribution):
    """
    Provision flocker on this node.
    """
    commands = (
        task_disable_firewall()
        + provision(
            package_source=package_source,
            distribution=node.distribution,
        )
    )
    run(
        username='root',
        address=node.address,
        commands=commands,
    )
    return node.address

    @property
    def name(self):
        return self._node.name


IMAGE_NAMES = {
    'fedora-20': u'Fedora 20 (Heisenbug) (PVHVM)',
}


def rackspace_provisioner(username, key, region, keyname):
    # Import these here, so that this can be imported without
    # installng libcloud.
    from libcloud.compute.providers import get_driver, Provider
    monkeypatch()
    driver = get_driver(Provider.RACKSPACE)(
        key=username,
        secret=key,
        region=region)

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=lambda **kwargs: {
            "ex_config_drive": "true",
        },
        provision=provision_rackspace,
        default_size="performance1-2",
    )

    return provisioner
