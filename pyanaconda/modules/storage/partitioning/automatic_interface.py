#
# DBus interface for the auto partitioning module.
#
# Copyright (C) 2018 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
from pyanaconda.dbus.interface import dbus_interface
from pyanaconda.dbus.property import emits_properties_changed
from pyanaconda.dbus.typing import *  # pylint: disable=wildcard-import
from pyanaconda.modules.common.constants.objects import AUTO_PARTITIONING
from pyanaconda.modules.common.structures.partitioning import PartitioningRequest
from pyanaconda.modules.storage.partitioning.base_interface import PartitioningInterface


@dbus_interface(AUTO_PARTITIONING.interface_name)
class AutoPartitioningInterface(PartitioningInterface):
    """DBus interface for the auto partitioning module."""

    def connect_signals(self):
        """Connect the signals."""
        super().connect_signals()
        self.watch_property("Enabled", self.implementation.enabled_changed)
        self.watch_property("Request", self.implementation.request_changed)

    @property
    def Enabled(self) -> Bool:
        """Is the auto partitioning enabled?"""
        return self.implementation.enabled

    @emits_properties_changed
    def SetEnabled(self, enabled: Bool):
        """Is the auto partitioning enabled?

        :param enabled: True if the autopartitioning is enabled, otherwise False
        """
        self.implementation.set_enabled(enabled)

    @property
    def Request(self) -> Structure:
        """The partitioning request."""
        return PartitioningRequest.to_structure(self.implementation.request)

    @emits_properties_changed
    def SetRequest(self, request: Structure):
        """Set the partitioning request.

        :param request: a request
        """
        self.implementation.set_request(PartitioningRequest.from_structure(request))

    def RequiresPassphrase(self) -> Bool:
        """Is the default passphrase required?

        :return: True or False
        """
        return self.implementation.requires_passphrase()

    @emits_properties_changed
    def SetPassphrase(self, passphrase: Str):
        """Set a default passphrase for all encrypted devices.

        :param passphrase: a string with a passphrase
        """
        self.implementation.set_passphrase(passphrase)
