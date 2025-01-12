#
# Copyright (C) 2015 - 2017  Red Hat, Inc.
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
# Red Hat Author(s): Vratislav Podzimek <vpodzime@redhat.com>
#                    Vojtech Trefny <vtrefny@redhat.com>
#

"""Module with the BlivetGuiSpoke class."""

import gi
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from pyanaconda.ui.gui.spokes import NormalSpoke
from pyanaconda.ui.helpers import StorageCheckHandler
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.gui.spokes.lib.summary import ActionSummaryDialog
from pyanaconda.core.constants import THREAD_EXECUTE_STORAGE, THREAD_STORAGE
from pyanaconda.core.i18n import _, CN_, C_
from pyanaconda.storage.initialization import reset_bootloader
from pyanaconda.modules.common.errors.configuration import BootloaderConfigurationError
from pyanaconda.storage.execution import configure_storage
from pyanaconda.threading import threadMgr

from blivetgui import osinstall
from blivetgui.config import config

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

# export only the spoke, no helper functions, classes or constants
__all__ = ["BlivetGuiSpoke"]

class BlivetGuiSpoke(NormalSpoke, StorageCheckHandler):
    ### class attributes defined by API ###

    # list all top-level objects from the .glade file that should be exposed
    # to the spoke or leave empty to extract everything
    builderObjects = ["blivetGuiSpokeWindow"]

    # the name of the main window widget
    mainWidgetName = "blivetGuiSpokeWindow"

    # name of the .glade file in the same directory as this source
    uiFile = "spokes/blivet_gui.glade"

    # category this spoke belongs to
    category = SystemCategory

    # title of the spoke (will be displayed on the hub)
    title = CN_("GUI|Spoke", "_Blivet-GUI Partitioning")

    helpFile = "blivet-gui/index.page"

    ### methods defined by API ###
    def __init__(self, data, storage, payload):
        """
        :see: pyanaconda.ui.common.Spoke.__init__
        :param data: data object passed to every spoke to load/store data
                     from/to it
        :type data: pykickstart.base.BaseHandler
        :param storage: object storing storage-related information
                        (disks, partitioning, bootloader, etc.)
        :type storage: blivet.Blivet
        :param payload: object storing payload-related information
        :type payload: pyanaconda.payload.Payload
        """

        self._error = None
        self._back_already_clicked = False
        self._storage_playground = None
        self.label_actions = None
        self.button_reset = None
        self.button_undo = None

        StorageCheckHandler.__init__(self)
        NormalSpoke.__init__(self, data, storage, payload)

    def initialize(self):
        """
        The initialize method that is called after the instance is created.
        The difference between __init__ and this method is that this may take
        a long time and thus could be called in a separated thread.

        :see: pyanaconda.ui.common.UIObject.initialize

        """

        NormalSpoke.initialize(self)
        self.initialize_start()

        self._storage_playground = None

        config.log_dir = "/tmp"
        self.client = osinstall.BlivetGUIAnacondaClient()
        box = self.builder.get_object("BlivetGuiViewport")
        self.label_actions = self.builder.get_object("summary_label")
        self.button_reset = self.builder.get_object("resetAllButton")
        self.button_undo = self.builder.get_object("undoLastActionButton")

        config.default_fstype = self._storage.default_fstype

        self.blivetgui = osinstall.BlivetGUIAnaconda(self.client, self, box)

        # this needs to be done when the spoke is already "realized"
        self.entered.connect(self.blivetgui.ui_refresh)

        # set up keyboard shurtcuts for blivet-gui (and unset them after
        # user lefts the spoke)
        self.entered.connect(self.blivetgui.set_keyboard_shortcuts)
        self.exited.connect(self.blivetgui.unset_keyboard_shortcuts)

        self.initialize_done()

    def refresh(self):
        """
        The refresh method that is called every time the spoke is displayed.
        It should update the UI elements according to the contents of
        self.data.

        :see: pyanaconda.ui.common.UIObject.refresh

        """
        for thread_name in [THREAD_EXECUTE_STORAGE, THREAD_STORAGE]:
            threadMgr.wait(thread_name)

        self._back_already_clicked = False

        self._storage_playground = self.storage.copy()
        self.client.initialize(self._storage_playground)
        self.blivetgui.initialize()

        # if we re-enter blivet-gui spoke, actions from previous visit were
        # not removed, we need to update number of blivet-gui actions
        current_actions = self._storage_playground.devicetree.actions.find()
        if current_actions:
            self.blivetgui.set_actions(current_actions)

    def apply(self):
        """
        The apply method that is called when the spoke is left. It should
        update the contents of self.data with values set in the GUI elements.
        """
        pass

    @property
    def indirect(self):
        return True

    # This spoke has no status since it's not in a hub
    @property
    def status(self):
        return None

    def clear_errors(self):
        self._error = None
        self.clear_info()

    def _do_check(self):
        self.clear_errors()
        StorageCheckHandler.errors = []
        StorageCheckHandler.warnings = []

        # We can't overwrite the main Storage instance because all the other
        # spokes have references to it that would get invalidated, but we can
        # achieve the same effect by updating/replacing a few key attributes.
        self.storage.devicetree._devices = self._storage_playground.devicetree._devices
        self.storage.devicetree._actions = self._storage_playground.devicetree._actions
        self.storage.devicetree._hidden = self._storage_playground.devicetree._hidden
        self.storage.devicetree.names = self._storage_playground.devicetree.names
        self.storage.roots = self._storage_playground.roots

        # set up bootloader and check the configuration
        try:
            configure_storage(self.storage, interactive=True)
        except BootloaderConfigurationError as e:
            StorageCheckHandler.errors = str(e).split("\n")
            reset_bootloader(self.storage)

        StorageCheckHandler.check_storage(self)

        if self.errors:
            self.set_warning(_("Error checking storage configuration.  <a href=\"\">Click for details</a> or press Done again to continue."))
        elif self.warnings:
            self.set_warning(_("Warning checking storage configuration.  <a href=\"\">Click for details</a> or press Done again to continue."))

        # on_info_bar_clicked requires self._error to be set, so set it to the
        # list of all errors and warnings that storage checking found.
        self._error = "\n".join(self.errors + self.warnings)

        return self._error == ""

    def activate_action_buttons(self, activate):
        self.button_undo.set_sensitive(activate)
        self.button_reset.set_sensitive(activate)

    ### handlers ###
    def on_info_bar_clicked(self, *args):
        log.debug("info bar clicked: %s (%s)", self._error, args)
        if not self._error:
            return

        dlg = Gtk.MessageDialog(flags=Gtk.DialogFlags.MODAL,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.CLOSE,
                                message_format=str(self._error))
        dlg.set_decorated(False)

        with self.main_window.enlightbox(dlg):
            dlg.run()
            dlg.destroy()

    def on_back_clicked(self, button):
        # Clear any existing errors
        self.clear_errors()

        # If back has been clicked on once already and no other changes made on the screen,
        # run the storage check now.  This handles displaying any errors in the info bar.
        if not self._back_already_clicked:
            self._back_already_clicked = True

            # If we hit any errors while saving things above, stop and let the
            # user think about what they have done
            if self._error is not None:
                return

            if not self._do_check():
                return

        self._storage_playground.devicetree.actions.prune()
        self._storage_playground.devicetree.actions.sort()
        actions = self._storage_playground.devicetree.actions.find()

        if actions:
            dialog = ActionSummaryDialog(self.data, actions)
            dialog.refresh()

            with self.main_window.enlightbox(dialog.window):
                rc = dialog.run()

            if rc != 1:
                # Cancel.  Stay on the blivet-gui screen.
                return

        NormalSpoke.on_back_clicked(self, button)

    def on_summary_button_clicked(self, _button):
        self.blivetgui.show_actions()

    def on_undo_action_button_clicked(self, _button):
        self.blivetgui.actions_undo()

    # This callback is for the button that just resets the UI to anaconda's
    # current understanding of the disk layout.
    def on_reset_button_clicked(self, *args):
        msg = _("Continuing with this action will reset all your partitioning selections "
                "to their current on-disk state.")

        dlg = Gtk.MessageDialog(flags=Gtk.DialogFlags.MODAL,
                                message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.NONE,
                                message_format=msg)
        dlg.set_decorated(False)
        dlg.add_buttons(C_("GUI|Custom Partitioning|Reset Dialog", "_Reset selections"), 0,
                        C_("GUI|Custom Partitioning|Reset Dialog", "_Preserve current selections"), 1)
        dlg.set_default_response(1)

        with self.main_window.enlightbox(dlg):
            rc = dlg.run()
            dlg.destroy()

        if rc == 0:
            self.refresh()
            self.blivetgui.reload()

            # XXX: Reset currently preserves actions set in previous runs
            # of the spoke, so we need to 're-add' these to the ui
            current_actions = self._storage_playground.devicetree.actions.find()
            if current_actions:
                self.blivetgui.set_actions(current_actions)
