# Methods and API for anaconda/firstboot 3rd party addons
#
# Copyright (C) 2012  Red Hat, Inc.
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

__all__ = ["AddonSection", "AddonRegistry", "AddonData", "collect_addon_paths"]

import os
import functools
from pykickstart.sections import Section

from pyanaconda.progress import progress_message
from pyanaconda.core.i18n import N_

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

PLACEHOLDER_NAME = "ADDON_placeholder"

def collect_addon_paths(toplevel_addon_paths, ui_subdir="gui"):
    """This method looks into the directories present
       in toplevel_addon_paths and registers each subdirectory
       as a new addon identified by that subdirectory name.

       It then registers spokes, categories and data (ks)
       paths for the application to use. By default is looks
       for spokes and categories in <addon>/gui/ subdirectory
       but that can be changed using the ui_subdir argument."""

    module_paths = {
        "spokes": [],
        "ks": [],
        "categories": []
        }

    for path in toplevel_addon_paths:
        try:
            directories = os.listdir(path)
        except OSError:
            directories = []

        for addon_id in directories:
            addon_ks_path = os.path.join(path, addon_id, "ks")
            if os.path.isdir(addon_ks_path):
                module_paths["ks"].append(("%s.ks.%%s" % addon_id, addon_ks_path))
                log.debug('Loading ks section into module path for addon %s', addon_id)

            addon_spoke_path = os.path.join(path, addon_id, ui_subdir, "spokes")
            if os.path.isdir(addon_spoke_path):
                module_paths["spokes"].append(("%s.%s.spokes.%%s" % (addon_id, ui_subdir), addon_spoke_path))
                log.debug('Loading spokes into module path for addon %s', addon_id)

            addon_category_path = os.path.join(path, addon_id, "categories")
            if os.path.isdir(addon_category_path):
                module_paths["categories"].append(("%s.categories.%%s" % addon_id, addon_category_path))
                log.debug('Loading categories into module path for addon %s', addon_id)

    return module_paths

class AddonRegistry(object):
    """This class represents the ksdata.addons object and
       maintains the ids and data structures for loaded
       addons.

       It acts as a proxy during kickstart save.
    """

    def __init__(self, dictionary):
        self.__dict__ = dictionary

    def __str__(self):
        return functools.reduce(lambda acc, id_addon: acc + str(id_addon[1]),
                                self.__dict__.items(), "")

    def execute(self, storage, ksdata, users, payload):
        """This method calls execute on all the registered addons."""
        for v in self.__dict__.values():
            if hasattr(v, "execute"):
                progress_message(N_("Executing %s addon") % v.name)
                v.execute(storage, ksdata, users, payload)

    def setup(self, storage, ksdata, payload):
        """This method calls setup on all the registered addons."""
        # filter out placeholders (should be imported now)
        d = {}
        for k, v in self.__dict__.items():
            if not v.name == PLACEHOLDER_NAME:
                d[k] = v
            else:
                log.warning("Removing placeholder for addon %s. Addon wasn't imported!", k)

        self.__dict__ = d
        for v in self.__dict__.values():
            if hasattr(v, "setup"):
                progress_message(N_("Setting up %s addon") % v.name)
                v.setup(storage, ksdata, payload)


class AddonData(object):
    """This is a common parent class for loading and storing
       3rd party data to kickstart. It is instantiated by
       kickstart parser and stored as ksdata.addons.<name>
       to be used in the user interfaces.

       The mandatory method handle_line receives all lines
       from the corresponding addon section in kickstart and
       the mandatory __str__ implementation is responsible for
       returning the proper kickstart text (to be placed into
       the %addon section) back.

       There is also a mandatory method execute, which should
       make all the described changes to the installed system.
    """

    def __init__(self, name):
        self.name = name
        self.content = ""
        self.header_args = ""

    def __str__(self):
        return "%%addon %s %s\n%s%%end\n" % (self.name, self.header_args, self.content)

    def setup(self, storage, ksdata, payload):
        """Make the changes to the install system.

           This method is called before the installation
           is started and directly from spokes. It must be possible
           to call it multiple times without breaking the environment."""
        log.warning("Addon %s doesn't have setup method!", self.name)

    def execute(self, storage, ksdata, users, payload):
        """Make the changes to the underlying system.

           This method is called only once in the post-install
           setup phase.
        """
        log.warning("Addon %s doesn't have execute method!", self.name)

    def handle_header(self, lineno, args):
        """Process additional arguments to the %addon line.

           This function receives any arguments on the %addon line after the
           addon ID. For example, for the line:

               %addon com_example_foo --argument='example'

           This function would be called with args=["--argument='example'"].

           By default AddonData.handle_header just preserves the passed
           arguments by storing them and adding them to the __str__ output.

        """

        if args:
            self.header_args += " ".join(args)

    def handle_line(self, line):
        """Process one kickstart line."""
        self.content += line

    def finalize(self):
        """No additional data will come.

           Addon should check if all mandatory attributes were populated.
        """
        pass

class AddonSection(Section):
    sectionOpen = "%addon"

    def __init__(self, *args, **kwargs):
        Section.__init__(self, *args, **kwargs)
        self.addon_id = None

    def handleLine(self, line):
        if not self.handler:
            return

        if not self.addon_id:
            return

        addon = getattr(self.handler.addons, self.addon_id)
        addon.handle_line(line)

    def handleHeader(self, lineno, args):
        """Process the arguments to the %addon header."""
        super().handleHeader(lineno, args)
        self.addon_id = args[1]

        # If the addon is not registered, create dummy placeholder for it.
        # If not replaced, the placeholder will be removed in the setup method.
        if self.addon_id and not hasattr(self.handler.addons, self.addon_id):
            setattr(self.handler.addons, self.addon_id, AddonData(PLACEHOLDER_NAME))

        # Parse additional arguments to %addon with the AddonData handler
        addon = getattr(self.handler.addons, self.addon_id)
        addon.handle_header(lineno, args[2:])

    def finalize(self):
        """Let addon know no additional data will come."""
        super().finalize()

        addon = getattr(self.handler.addons, self.addon_id)
        addon.finalize()
