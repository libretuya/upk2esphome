#  Copyright (c) Kuba Szczodrzyński 2023-9-4.

from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigData:
    type: "Type"
    data: dict
    extras: dict

    class Type(Enum):
        CLOUDCUTTER = "Cloudcutter JSON"
        STORAGE = "Storage JSON"
        RAW = "Raw UPK"

    @staticmethod
    def build(data: dict, extras: dict) -> "ConfigData":
        type = None
        if "schemas" in data and "profiles" in data:
            type = ConfigData.Type.CLOUDCUTTER
        elif "gw_bi" in data:
            type = ConfigData.Type.STORAGE
        elif "Jsonver" in data or "jv" in data or "crc" in data:
            type = ConfigData.Type.RAW
            data = dict(sorted(data.items()))
        else:
            raise ValueError("Couldn't recognize input data")
        return ConfigData(type, data, extras)

    @property
    def is_tuya_mcu(self) -> bool:
        match self.type:
            case ConfigData.Type.CLOUDCUTTER:
                profiles = self.data.get("profiles", [])
                profile = profiles and profiles[0] or {}
                name = profile.get("sub_name", None) or ""
                return name.startswith("bk7231") and "common" in name
            case ConfigData.Type.STORAGE:
                return "baud_cfg" in self.data or "uart_adapt_params" in self.data
            case ConfigData.Type.RAW:
                return False

    @property
    def upk(self) -> dict | None:
        match self.type:
            case ConfigData.Type.CLOUDCUTTER:
                return self.data.get("device_configuration", None)
            case ConfigData.Type.STORAGE:
                return self.data.get("user_param_key", None)
            case ConfigData.Type.RAW:
                return self.data

    @property
    def uart_config(self) -> dict | None:
        return self.data.get("baud_cfg", None) or self.data.get(
            "uart_adapt_params", None
        )

    @property
    def model(self) -> dict | None:
        return self.extras.get("model", None)

    @property
    def data_device(self) -> dict | None:
        match self.type:
            case ConfigData.Type.CLOUDCUTTER:
                profiles = self.data.get("profiles", [])
                profile = profiles and profiles[0] or {}
                name = profile.get("name", None) or ""
                return dict(
                    firmwareKey=self.data.get("key", None),
                    productKey=None,
                    factoryPin=None,
                    softwareVer=name.partition(" ")[0] or None,
                )
            case ConfigData.Type.STORAGE:
                gw_di = self.data.get("gw_di", {})
                gw_bi = self.data.get("gw_bi", {})
                return dict(
                    firmwareKey=gw_di.get("firmk", None),
                    productKey=gw_di.get("pk", None),
                    factoryPin=gw_bi.get("fac_pin", None),
                    softwareVer=gw_di.get("swv", None),
                )

    @property
    def data_software(self) -> dict | None:
        if self.type != ConfigData.Type.STORAGE:
            return None
        gw_di = self.data.get("gw_di", {})
        return dict(
            bv=gw_di.get("bv", None),
            pv=gw_di.get("pv", None),
            cadv=gw_di.get("cadv", None),
            cdv=gw_di.get("cdv", None),
        )

    @property
    def data_license(self) -> dict | None:
        if self.type != ConfigData.Type.STORAGE:
            return None
        gw_bi = self.data.get("gw_bi", {})
        if gw_bi.get("ap_ssid", "") == "A":
            return None
        return dict(
            uuid=gw_bi.get("uuid", None),
            authKey=gw_bi.get("authKey", None),
        )