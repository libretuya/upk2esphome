#  Copyright (c) Kuba Szczodrzyński 2023-5-13.

import json
import os
from logging import debug, error, info, warning
from os.path import dirname, isfile

import wx
import wx.adv
import wx.xrc
from ltchiptool.gui.base.zc import ZeroconfBase
from ltchiptool.gui.panels.base import BasePanel
from ltchiptool.gui.utils import on_event
from ltchiptool.util.logging import LoggingHandler
from zeroconf import IPVersion, ServiceInfo

from upk2esphome import Opts, YamlResult, upk2esphome
from upk2esphome.const import DISCLAIMER_TEXT, TUYAMCU_MESSAGE

from .common import cloudcutter_get_device, cloudcutter_list_devices
from .work import UpkThread
from .work_schema import UpkSchemaThread

ZEROCONF_SERVICE = "_esphomelib._tcp.local."


# noinspection PyPep8Naming
class UpkPanel(BasePanel, ZeroconfBase):
    last_dir: str = None
    last_url: str = None
    logs_shown: bool = False
    disclaimer_shown: bool = False
    kickstart_devices: dict[str, str] = None
    _result: YamlResult | None = None
    _schema_response: dict | None = None

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRCFile("upk2esphome.xrc")
        self.LoadXRC("UpkPanel")
        self.AddToNotebook("UPK2ESPHome")

        self.Notebook: wx.Notebook = self.FindWindowByName("notebook_upk", self)

        self.Kickstart: wx.adv.CommandLinkButton = self.BindButton(
            "button_kickstart",
            self.OnDoKickstartClick,
        )
        self.Kickstart.Bind(wx.EVT_CONTEXT_MENU, self.OnDoKickstartRightClick)
        self.BindButton("button_cloudcutter", self.OnDoCloudcutterClick)
        self.BindButton("button_dump", self.OnDoDumpClick)

        self.Opts: dict[str, wx.CheckBox | wx.TextCtrl] = {
            "esphome_block": self.BindCheckBox("opts_esphome_block"),
            "name_mac": self.BindCheckBox("opts_name_mac"),
            "common": self.BindCheckBox("opts_common"),
            "web_server": self.BindCheckBox("opts_web_server"),
            "restart": self.BindCheckBox("opts_restart"),
            "uptime": self.BindCheckBox("opts_uptime"),
            "lt_version": self.BindCheckBox("opts_lt_version"),
            "wifi_ssid": self.BindTextCtrl("opts_wifi_ssid"),
            "wifi_password": self.BindTextCtrl("opts_wifi_password"),
            "ota_password": self.BindTextCtrl("opts_ota_password"),
            "api_password": self.BindTextCtrl("opts_api_password"),
        }
        self.BindButton("button_generate", self.OnGenerateClick)
        self.BindButton("button_esphome_copy", self.OnEsphomeCopyClick)

        self.TextEsphome = self.BindTextCtrl("input_esphome")
        self.TextData = self.BindTextCtrl("input_source_data")
        self.TextExtras = self.BindTextCtrl("input_source_extras")
        self.LabelData = self.FindStaticText("text_source_data")
        self.LabelExtras = self.FindStaticText("text_source_extras")

        self.LabelsGuided = [
            self.FindStaticText("text_guided_1"),
            self.FindStaticText("text_guided_2"),
        ]
        self.SchemaInputsDevice: dict[str, wx.TextCtrl] = {
            "firmwareKey": self.FindWindowByName("input_firmware_key", self),
            "productKey": self.FindWindowByName("input_product_key", self),
            "factoryPin": self.FindWindowByName("input_factory_pin", self),
            "softwareVer": self.FindWindowByName("input_software_ver", self),
        }
        self.SchemaInputsLicense: dict[str, wx.TextCtrl] = {
            "uuid": self.FindWindowByName("input_uuid", self),
            "authKey": self.FindWindowByName("input_auth_key", self),
        }
        self.BindButton("button_schema_download", self.OnSchemaDownloadClick)
        self.SchemaDeviceCategory = self.FindWindowByName("input_device_category", self)
        self.SchemaDeviceName = self.FindWindowByName("input_device_name", self)
        self.ButtonSchemaResponse = self.BindButton(
            "button_schema_response", self.OnSchemaResponseClick
        )
        self.BindWindow(
            "collapsible_schema",
            (wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnSchemaCollapsibleClick),
        )

        self.EnableFileDrop()

        default_opts = Opts()
        for key, value in Opts.FLAGS.items():
            if key not in self.Opts:
                continue
            self.Opts[key].SetValue(getattr(default_opts, key))
        for key, value in Opts.INPUTS.items():
            if key not in self.Opts:
                continue
            self.Opts[key].ChangeValue(getattr(default_opts, key))

        self.last_result = None

    def GetSettings(self) -> dict:
        return dict(
            opts={key: value.GetValue() for key, value in self.Opts.items()},
            last_dir=self.last_dir,
            last_url=self.last_url,
            disclaimer_shown=self.disclaimer_shown,
        )

    def SetSettings(
        self,
        opts: dict = None,
        last_dir: str = None,
        last_url: str = None,
        disclaimer_shown: bool = None,
        **_,
    ):
        if opts:
            for key, value in opts.items():
                if key in self.Opts:
                    self.Opts[key].SetValue(value)
        if last_dir:
            self.last_dir = last_dir
        if last_url:
            self.last_url = last_url
        if disclaimer_shown is not None:
            self.disclaimer_shown = disclaimer_shown

    def OnActivate(self):
        self.AddZeroconfBrowser(ZEROCONF_SERVICE)

    def OnDeactivate(self):
        self.StopZeroconf()

    def OnUpdate(self, target: wx.Window = None):
        if target is None:
            return
        debug(f"OnUpdate, target: {type(target)}")
        data = self.data
        if not data:
            self.TextEsphome.Clear()
            self.logs_shown = False
            return
        if target == self.TextData or target == self.TextExtras:
            # show error logs again after changing input data
            self.logs_shown = False

        if not self.disclaimer_shown:
            wx.MessageBox(
                message=DISCLAIMER_TEXT,
                caption="Disclaimer",
                style=wx.ICON_WARNING,
            )
            self.disclaimer_shown = True

        opts = Opts(**self.GetSettings()["opts"])
        yr = upk2esphome(data, opts)
        # update UI according to the generation result
        self.last_result = yr
        if not yr.errors:
            # navigate to Options page if successful
            self.Notebook.SetSelection(1)

        if not self.logs_shown:
            # show errors only once, then allow to change generation options
            self.logs_shown = True
            # print messages to logger
            for line in yr.errors:
                error(f"UPK: {line}")
            for line in yr.warnings:
                warning(f"UPK: {line}")
            for line in yr.logs:
                info(f"UPK: {line}")
            # ask about downloading device schema
            if yr.needs_tuyamcu_model:
                if self.extras:
                    # warn when extras filled but model still needed
                    wx.MessageBox(
                        message=(
                            "Incorrect device schema model\n\n"
                            "UPK2ESPHome couldn't generate TuyaMCU config based on "
                            "the provided schema model.\n\n"
                            "If you feel that's an error, try downloading "
                            "the schema again."
                        ),
                        caption="Warning",
                        style=wx.ICON_WARNING,
                    )
                else:
                    # otherwise ask the user to fill extras
                    dialog = wx.MessageDialog(
                        self,
                        message=TUYAMCU_MESSAGE.strip(),
                        caption="Found TuyaMCU device",
                        style=wx.ICON_INFORMATION | wx.OK | wx.CANCEL,
                    )
                    selection = dialog.ShowModal()
                    dialog.Destroy()
                    if selection == wx.ID_OK:
                        self.Notebook.SetSelection(4)
                        return
            # show other errors and warnings
            if yr.errors:
                wx.MessageBox(
                    message="\n".join(yr.errors),
                    caption="Error",
                    style=wx.ICON_ERROR,
                )
            elif yr.warnings:
                message = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(yr.warnings))
                wx.MessageBox(
                    message="While generating YAML:\n\n" + message,
                    caption="Warning",
                    style=wx.ICON_WARNING,
                )

    def OnStorageData(self, storage: dict):
        self.data = storage
        self.DoUpdate()

    def OnStorageError(self, error_text: str):
        self.data = None
        self.DoUpdate()
        wx.MessageBox(
            message=error_text,
            caption="Error",
            style=wx.ICON_ERROR,
        )

    def OnSchemaResponse(self, response: dict):
        self.schema_response = response
        self.DoUpdate()

    def OnSchemaError(self, error_text: str):
        self.schema_response = None
        self.DoUpdate()
        wx.MessageBox(
            message=error_text,
            caption="Error",
            style=wx.ICON_ERROR,
        )

    def OnFileDrop(self, *files):
        if not files:
            return
        file = files[0]
        if not isfile(file):
            return
        self.last_dir = dirname(file)
        work = UpkThread(
            file=file,
            on_storage=self.OnStorageData,
            on_error=self.OnStorageError,
        )
        self.StartWork(work)

    def OnZeroconfUpdate(self, services: dict[str, ServiceInfo]):
        if self.kickstart_devices:
            self.kickstart_devices.clear()
        for serv_info in services.values():
            if not serv_info.properties:
                continue
            address = serv_info.parsed_scoped_addresses(version=IPVersion.V4Only)[0]
            project_name = serv_info.properties.get(b"project_name", None)
            if not project_name:
                continue

            label = f"{serv_info.server.rstrip('.')} ({address})"
            if self.kickstart_devices is None:
                self.kickstart_devices = {}
            self.kickstart_devices[label] = address
        if self.kickstart_devices:
            self.Kickstart.SetNote(
                f"Found {len(self.kickstart_devices)} device(s): "
                + ", ".join(self.kickstart_devices.keys())
                + "\n"
                "Right-click to enter IP manually"
            )
        elif self.kickstart_devices is not None:
            self.Kickstart.SetNote("Found no Kickstart devices")

    @on_event
    def OnDoKickstartClick(self):
        self.OnDoKickstart(force_custom=False)

    @on_event
    def OnDoKickstartRightClick(self):
        self.OnDoKickstart(force_custom=True)

    def OnDoKickstart(self, force_custom: bool = False):
        devices = dict(self.kickstart_devices or {})
        if len(devices) == 0 or force_custom:
            dialog = wx.TextEntryDialog(
                self,
                message="Enter URL (or IP address) of Kickstart dashboard:",
                caption="Kickstart URL",
                value=self.last_url or "",
            )
            if dialog.ShowModal() != wx.ID_OK:
                dialog.Destroy()
                return
            url = dialog.GetValue().strip()
            dialog.Destroy()
            if not url:
                return
        elif len(devices) != 1:
            dialog = wx.SingleChoiceDialog(
                self,
                message=(
                    "We've found a few devices running ESPHome-Kickstart. "
                    "Please choose one:"
                ),
                caption="Kickstart device",
                choices=list(devices.keys()),
            )
            if dialog.ShowModal() != wx.ID_OK:
                dialog.Destroy()
                return
            choice = dialog.GetStringSelection()
            dialog.Destroy()
            if choice not in devices:
                return
            url = devices[choice]
        else:
            url = list(devices.values())[0]

        debug(f"Kickstart URL: {url}")
        self.last_url = url
        work = UpkThread(
            url=url,
            on_storage=self.OnStorageData,
            on_error=self.OnStorageError,
        )
        self.StartWork(work)

    @on_event
    def OnDoCloudcutterClick(self):
        self.DisableAll()
        try:
            devices_slug, devices_name = cloudcutter_list_devices()
            self.EnableAll()
        except Exception as e:
            self.EnableAll()
            LoggingHandler.get().emit_exception(e)
            return

        dialog = wx.SingleChoiceDialog(
            self,
            message="Choose a Cloudcutter profile, that matches your particular device:",
            caption="Cloudcutter profile",
            choices=devices_name,
        )
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return
        selection = dialog.GetSelection()
        dialog.Destroy()

        self.DisableAll()
        try:
            device = cloudcutter_get_device(devices_slug[selection])
            self.EnableAll()
        except Exception as e:
            self.EnableAll()
            LoggingHandler.get().emit_exception(e)
            return

        self.data = device

    @on_event
    def OnDoDumpClick(self):
        title = "Open file"
        flags = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        init_dir = self.last_dir or os.getcwd()
        with wx.FileDialog(self, title, init_dir, style=flags) as dialog:
            dialog: wx.FileDialog
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            file = dialog.GetPath()
            self.last_dir = dirname(file)
            work = UpkThread(
                file=file,
                on_storage=self.OnStorageData,
                on_error=self.OnStorageError,
            )
            self.StartWork(work)

    @on_event
    def OnGenerateClick(self):
        self.Notebook.SetSelection(2)

    @on_event
    def OnEsphomeCopyClick(self):
        text = self.TextEsphome.GetValue()
        clip = wx.TextDataObject()
        clip.SetText(text)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(clip)
            wx.TheClipboard.Flush()
            self.TextEsphome.SelectAll()

    @on_event
    def OnSchemaDownloadClick(self):
        work = UpkSchemaThread(
            device=self.schema_device,
            software=(
                self.last_result
                and self.last_result.config
                and self.last_result.config.data_software
            ),
            license_=self.schema_license,
            on_success=self.OnSchemaResponse,
            on_error=self.OnSchemaError,
        )
        self.StartWork(work)

    @on_event
    def OnSchemaResponseClick(self):
        if not self.schema_response:
            self.ButtonSchemaResponse.Enable(False)
            return
        wx.MessageBox(
            message=json.dumps(self.schema_response, indent=4),
            caption="Schema API response",
            style=wx.ICON_INFORMATION,
        )

    @on_event
    def OnSchemaCollapsibleClick(self):
        page: wx.NotebookPage = self.Notebook.GetPage(4)
        page.Layout()
        page.Update()

    @property
    def data(self) -> dict | None:
        text = self.TextData.GetValue() or None
        return text and json.loads(text)

    @data.setter
    def data(self, value: dict | None) -> None:
        text = value and json.dumps(value, indent=4) or ""
        self.TextData.ChangeValue(text or "")
        self.TextExtras.ChangeValue("")
        self.DoUpdate(self.TextData)

    @property
    def extras(self) -> dict | None:
        text = self.TextExtras.GetValue() or None
        return text and json.loads(text)

    @extras.setter
    def extras(self, value: dict | None) -> None:
        text = value and json.dumps(value, indent=4) or ""
        self.TextExtras.ChangeValue(text or "")
        self.DoUpdate(self.TextExtras)

    @property
    def last_result(self) -> YamlResult | None:
        return self._result

    @last_result.setter
    def last_result(self, value: YamlResult | None) -> None:
        self._result = yr = value
        config = yr and yr.config

        is_valid = yr and not yr.errors or False
        is_guided = is_valid and yr.needs_tuyamcu_model
        self.Notebook.GetPage(1).Enable(is_valid)
        self.Notebook.GetPage(2).Enable(is_valid)
        self.TextEsphome.ChangeValue(is_valid and yr.text or "")

        self.schema_device = config and config.data_device
        self.schema_license = config and config.data_license

        for label in self.LabelsGuided:
            label.Show(is_guided)
        for input in self.SchemaInputsDevice.values():
            input.Enable(not is_guided)

        page: wx.NotebookPage = self.Notebook.GetPage(4)
        page.Layout()
        page.Update()
        # for now, only allow pulling schema for TuyaMCU devices
        page.Enable(is_guided)

    @property
    def schema_device(self) -> dict:
        value = {}
        for key, input in self.SchemaInputsDevice.items():
            value[key] = input.GetValue() or None
        return value

    @schema_device.setter
    def schema_device(self, value: dict | None) -> None:
        value = value or {}
        for key, input in self.SchemaInputsDevice.items():
            text = value.get(key, None)
            input.ChangeValue(text or "")

    @property
    def schema_license(self) -> dict:
        value = {}
        for key, input in self.SchemaInputsLicense.items():
            value[key] = input.GetValue() or None
        return value

    @schema_license.setter
    def schema_license(self, value: dict | None) -> None:
        value = value or {}
        for key, input in self.SchemaInputsLicense.items():
            text = value.get(key, None)
            input.ChangeValue(text or "")

    @property
    def schema_response(self) -> dict | None:
        return self._schema_response

    @schema_response.setter
    def schema_response(self, value: dict | None) -> None:
        self._schema_response = value
        debug(f"Received schema response ({type(value).__name__})")

        active_response = value.get("activeResponse", {})
        model_response = value.get("modelResponse", {})
        details_response = value.get("detailsResponse", {})

        model = model_response.get("model", {})
        model_id = model.get("modelId", None)
        schema_id = active_response.get("schemaId", None)
        category_name = details_response.get("category_name", "Unknown")
        category = details_response.get("category", "unk")
        name = details_response.get("model", "")

        self.SchemaDeviceCategory.ChangeValue(
            category_name
            and f"{category_name} ({category})"
            or " ".join(value.get("errors", []))
        )
        self.SchemaDeviceName.ChangeValue(
            f"{name} - schema ID: {model_id or schema_id}"
        )

        if not model:
            wx.MessageBox(
                message=(
                    "Missing schema model description\n\n"
                    "The API response doesn't include the schema model.\n"
                    "Please inspect the response data and report an error "
                    "to the LibreTiny developers."
                ),
                caption="Error",
                style=wx.ICON_ERROR,
            )
            return

        yr = self.last_result
        if yr and yr.needs_tuyamcu_model:
            wx.MessageBox(
                message=(
                    "Fetched schema model\n\n"
                    "The schema model for TuyaMCU has been downloaded.\n\n"
                    "Press OK to continue setting up your ESPHome config."
                ),
                caption="Success",
                style=wx.ICON_INFORMATION,
            )
            self.extras = dict(
                model=model,
            )
