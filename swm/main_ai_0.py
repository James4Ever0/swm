"""SWM - Scrcpy Window Manager

Usage:
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <app_name> [<scrcpy_args>...]
  swm [options] app list [last_used] [type]
  swm [options] app search [type] [index]
  swm [options] app most-used [<count>]
  swm [options] app config show-default
  swm [options] app config <app_name> (show|edit)
  swm [options] session list [last_used]
  swm [options] session search [index]
  swm [options] session restore [session_name]
  swm [options] session (save|delete) <session_name>
  swm [options] device list [last_used]
  swm [options] device search [index]
  swm [options] device select <device_id>
  swm [options] device name <device_id> <device_alias>
  swm [options] baseconfig show [diagnostic]
  swm [options] baseconfig show-default
  swm [options] baseconfig edit
  swm --version
  swm --help

Options:
  -h --help     Show this screen.
  --version     Show version.
  -c --config=<config_file>
                Use a config file.
  -v --verbose  Enable verbose logging.
  -d --device=<device_selected>
                Device name or ID for executing the command.
  --debug       Debug mode, capturing all exceptions.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from datetime import datetime
from typing import Dict, List, Optional
import functools

import pandas
import omegaconf
import requests
import yaml
from docopt import docopt
from tinydb import Query, Storage, TinyDB

__version__ = "0.1.0"

# TODO: override icon with SCRCPY_ICON_PATH=<app_icon_path>


class NoDeviceError(ValueError): ...


class NoSelectionError(ValueError): ...


class NoConfigError(ValueError): ...


class NoBaseConfigError(ValueError): ...


class NoDeviceConfigError(ValueError): ...


class NoDeviceAliasError(ValueError): ...


class NoDeviceNameError(ValueError): ...


class NoDeviceIdError(ValueError): ...


def prompt_for_option_selection(
    options: List[str], prompt: str = "Select an option: "
) -> str:
    while True:
        print(prompt)
        for i, option in enumerate(options):
            print(f"{i + 1}. {option}")
        try:
            selection = int(input("Enter your choice: "))
            if 1 <= selection <= len(options):
                return options[selection - 1]
        except ValueError:
            pass


def reverse_text(text):
    return "".join(reversed(text))


def spawn_and_detach_process(cmd: List[str]):
    return subprocess.Popen(cmd, start_new_session=True)


def parse_scrcpy_app_list_output_single_line(text: str):
    ret = {}
    text = text.strip()

    package_type_symbol, rest = text.split(" ", maxsplit=1)

    reversed_text = reverse_text(rest)

    ret["type_symbol"] = package_type_symbol

    package_id_reverse, rest = reversed_text.split(" ", maxsplit=1)

    package_id = reverse_text(package_id_reverse)
    ret["id"] = package_id

    package_alias = reverse_text(rest).strip()

    ret["alias"] = package_alias
    return ret


def select_editor():
    unix_editors = ["vim", "nano", "vi", "emacs"]
    windows_editors = ["notepad"]
    cross_platform_editors = ["code"]

    possible_editors = unix_editors + windows_editors + cross_platform_editors

    for editor in possible_editors:
        editor_binpath = shutil.which(editor)
        if editor_binpath:
            print("Using editor:", editor_binpath)
            return editor_binpath
    print(
        "No editor found. Please install one of the following editors:",
        ", ".join(possible_editors),
    )


def edit_file(filepath: str, editor_binpath: str):
    execute_subprogram(editor_binpath, [filepath])


def edit_or_open_file(filepath: str):
    print("Editing file:", filepath)
    editor_binpath = select_editor()
    if editor_binpath:
        edit_file(filepath, editor_binpath)
    else:
        open_file_with_default_application(filepath)
    print("Done editing file:", filepath)


def open_file_with_default_application(filepath: str):
    system = platform.system()
    if system == "Darwin":  # macOS
        command = ["open", filepath]
    elif system == "Windows":  # Windows
        command = ["start", filepath]
    elif shutil.which("open"):  # those Linux OSes with "xdg-open"
        command = ["open", filepath]
    else:
        raise ValueError("Unsupported operating system.")
    subprocess.run(command, check=True)


def download_and_unzip(url, extract_dir):
    """
    Downloads a ZIP file from a URL and extracts it to the specified directory.

    Args:
        url (str): URL of the ZIP file to download.
        extract_dir (str): Directory path where contents will be extracted.
    """
    # Create extraction directory if it doesn't exist
    os.makedirs(extract_dir, exist_ok=True)

    # Stream download to a temporary file
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Raise error for bad status codes

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            # Write downloaded chunks to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            tmp_path = tmp_file.name

    # Extract the ZIP file
    with zipfile.ZipFile(tmp_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    # Clean up temporary file
    os.unlink(tmp_path)


def get_system_and_architecture():
    system = platform.system().lower()
    arch = platform.machine().lower()
    if arch == "x86_64":
        arch = "x64"
    elif arch == "aarch64":
        arch = "arm64"
    return system, arch


def collect_system_info_for_diagnostic():
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "architecture": platform.architecture(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


def pretty_print_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=4)


def print_diagnostic_info(program_specific_params):
    system_info = collect_system_info_for_diagnostic()
    print("System info:")
    print(pretty_print_json(system_info))
    print("\nProgram parameters:")
    print(pretty_print_json(program_specific_params))


def execute_subprogram(program_path, args):
    try:
        subprocess.run([program_path] + args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing {program_path}: {e}")
    except FileNotFoundError:
        print(f"Executable not found: {program_path}")


def search_or_obtain_binary_path_from_environmental_variable_or_download(
    cache_dir: str, bin_name: str
) -> str:
    # Adjust binary name for platform
    bin_env_name = bin_name.upper()
    platform_specific_name = bin_name.lower()

    if platform.system() == "Windows":
        platform_specific_name += ".exe"

    # 1. Check environment variable
    env_path = os.environ.get(bin_env_name)
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Check in PATH
    path_path = shutil.which(platform_specific_name)
    if path_path:
        return path_path

    # 3. Check in cache directory
    cache_path = os.path.join(cache_dir, "bin", platform_specific_name)
    if os.path.exists(cache_path):
        return cache_path

    # 4. Not found anywhere - attempt to download
    return download_binary_into_cache_dir_and_return_path(cache_dir, bin_name)


def download_binary_into_cache_dir_and_return_path(
    cache_dir: str, bin_name: str
) -> str:
    # Placeholder implementation - would download the binary
    bin_dir = os.path.join(cache_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # For demonstration purposes, we'll just create an empty file
    bin_path = os.path.join(bin_dir, bin_name)
    if platform.system() == "Windows":
        bin_path += ".exe"

    print(f"WARNING: Creating placeholder binary at {bin_path}")
    with open(bin_path, "w") as f:
        f.write("#!/bin/sh\necho 'Placeholder binary for SWM'")

    if platform.system() != "Windows":
        os.chmod(bin_path, 0o755)

    return bin_path


class ADBStorage(Storage):
    def __init__(self, filename, adb_wrapper: "AdbWrapper", enable_read_cache=True):
        self.filename = filename
        self.adb_wrapper = adb_wrapper
        adb_wrapper.create_file_if_not_exists(self.filename)
        self.enable_read_cache = enable_read_cache
        self.read_cache = None

    def read(self):
        try:
            if self.enable_read_cache:
                if self.read_cache is None:
                    content = self.adb_wrapper.read_file(self.filename)
                    self.read_cache = content
                else:
                    content = self.read_cache
            else:
                content = self.adb_wrapper.read_file(self.filename)
            data = json.loads(content)
            return data
        except json.JSONDecodeError:
            return None

    def write(self, data):
        content = json.dumps(data)
        self.adb_wrapper.write_file(self.filename, content)
        if self.enable_read_cache:
            self.read_cache = content

    def close(self):
        pass


class SWMOnDeviceDatabase:
    def __init__(self, db_path: str, adb_wrapper: "AdbWrapper"):
        self.db_path = db_path
        self.storage = functools.partial(ADBStorage, adb_wrapper=adb_wrapper)
        self._db = TinyDB(db_path, storage=self.storage)

    def write_app_last_used_time(
        self, device_id, app_id: str, last_used_time: datetime
    ):
        AppUsage = Query()

        # Upsert document: update if exists, insert otherwise
        self._db.table("app_usage").upsert(
            {
                "device_id": device_id,
                "app_id": app_id,
                "last_used_time": last_used_time.isoformat(),
            },
            (AppUsage.device_id == device_id) & (AppUsage.app_id == app_id),
        )

    def get_app_last_used_time(self, device_id, app_id: str) -> datetime:
        AppUsage = Query()

        # Search for matching document
        result = self._db.table("app_usage").get(
            (AppUsage.device_id == device_id) & (AppUsage.app_id == app_id)
        )

        # Return datetime object if found, None otherwise
        return datetime.fromisoformat(result["last_used_time"]) if result else None


class SWM:
    def __init__(self, config: omegaconf.DictConfig):
        self.config = config
        self.cache_dir = config.cache_dir
        self.bin_dir = os.path.join(self.cache_dir, "bin")
        os.makedirs(self.bin_dir, exist_ok=True)

        # Initialize binaries
        self.adb = self._get_binary("adb")
        self.scrcpy = self._get_binary("scrcpy")
        self.fzf = self._get_binary("fzf")

        # Initialize components
        self.adb_wrapper = AdbWrapper(self.adb, self.config)
        self.scrcpy_wrapper = ScrcpyWrapper(self.scrcpy, self.config)
        self.fzf_wrapper = FzfWrapper(self.fzf)

        # Device management
        self.current_device = None

        # Initialize managers
        self.app_manager = AppManager(self)
        self.session_manager = SessionManager(self)
        self.device_manager = DeviceManager(self)

        self.on_device_db = None

    def load_swm_on_device_db(self):
        db_path = os.path.join(self.config.android_session_storage_path, "db.json")
        self.on_device_db = SWMOnDeviceDatabase(db_path, self.adb_wrapper)

    def _get_binary(self, name: str) -> str:
        return search_or_obtain_binary_path_from_environmental_variable_or_download(
            self.cache_dir, name
        )

    def set_current_device(self, device_id: str):
        self.current_device = device_id
        self.adb_wrapper.set_device(device_id)
        self.scrcpy_wrapper.set_device(device_id)

    def get_device_architecture(self) -> str:
        return self.adb_wrapper.get_device_architecture()

    def infer_current_device(self, default_device: str):
        all_devices = self.adb_wrapper.list_device_ids()
        if len(all_devices) == 0:
            # no devices.
            print("No device is online")
            return
        elif len(all_devices) == 1:
            # only one device.
            device = all_devices[0]
            if device != default_device:
                print(
                    "Device selected by config (%s) is not online, using the only device online (%s)"
                    % (default_device, device)
                )
            return device
        else:
            print("Multiple device online")
            if default_device in all_devices:
                print("Using selected device:", default_device)
                return default_device
            else:
                print(
                    "Device selected by config (%s) is not online, please select one."
                    % default_device
                )
                prompt_for_device = f"Select a device from: "
                # TODO: input numbers or else
                # TODO: show detailed info per device, such as device type, last swm use time, alias, device model, android info, etc...
                selected_device = prompt_for_option_selection(
                    all_devices, prompt_for_device
                )
                return selected_device


def load_and_print_as_dataframe(
    list_of_dict, additional_fields={}, show=True, sort_columns=True
):

    df = pandas.DataFrame(list_of_dict)
    if sort_columns:
        sorted_columns = sorted(df.columns)

        # Reindex the DataFrame with the sorted column order
        df = df[sorted_columns]
    for key, value in additional_fields.items():
        if value is False:
            df.drop(key, axis=1, inplace=True)
    formatted_output = df.to_string(index=False)
    if show:
        print(formatted_output)
    return formatted_output


class AppManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config

    def get_app_last_used_time_from_device(self):
        last_used_time = self.swm.adb_wrapper.execute()
        return last_used_time

    def get_app_last_used_time_from_db(self, package_id: str):
        device_id = self.swm.current_device
        last_used_time = self.swm.on_device_db.get_app_last_used_time(
            device_id, package_id
        )
        return last_used_time

    def search(self, index: bool):
        apps = self.list()
        items = []
        for i, it in enumerate(apps):
            line = f"{it['alias']}\t{it['id']}"
            if index:
                line = f"[{i+1}]\t{line}"
            items.append(line)
        selected = self.swm.fzf_wrapper.select_item(items)
        if selected:
            package_id = selected.split("\t")[-1]
            return package_id
        else:
            return None

    def list(
        self,
        most_used: Optional[int] = None,
        print_formatted: bool = False,
        additional_fields: dict = {},
    ):
        if most_used:
            apps = self.list_most_used_apps(most_used)
        else:
            apps = self.list_all_apps()

        if print_formatted:
            load_and_print_as_dataframe(apps, additional_fields=additional_fields)

        return apps

    def install_and_use_adb_keyboard(self): ...

    def retrieve_app_icon(self, package_id: str): ...

    def run(self, app_name: str, scrcpy_args: List[str] = None):
        # TODO: memorize the last scrcpy run args, by default in swm config
        # Get app config
        env = {}
        app_config = self.get_or_create_app_config(app_name)
        if app_config.get("use_adb_keyboard", False):
            self.install_and_use_adb_keyboard()
        if app_config.get("retrieve_app_icon", False):
            icon_path = self.retrieve_app_icon(app_name)
            env["SCRCPY_ICON_PATH"] = icon_path
        # Add window config if exists
        win = app_config.get("window", None)

        if scrcpy_args is None:
            scrcpy_args = app_config.get("scrcpy_args", None)

        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(
            app_name, window_params=win, scrcpy_args=scrcpy_args
        )

    def edit_app_config(self, app_name: str) -> bool:
        # return True if edited, else False
        print(f"Editing config for {app_name}")
        app_config_path = self.get_app_config_path(app_name)
        self.get_or_create_app_config(app_name)
        edit_or_open_file(app_config_path)

    def show_app_config(self, app_name: str):
        config = self.get_or_create_app_config(app_name)
        print(pretty_print_json(config))

    def get_app_config_path(self, app_name: str):

        app_config_dir = os.path.join(self.swm.cache_dir, "apps")
        os.makedirs(app_config_dir, exist_ok=True)

        app_config_path = os.path.join(app_config_dir, f"{app_name}.yaml")
        return app_config_path

    def get_or_create_app_config(self, app_name: str) -> Dict:
        app_config_path = self.get_app_config_path(app_name)

        if not os.path.exists(app_config_path):
            print("Creating default config for app:", app_name)
            # Write default YAML template with comments
            with open(app_config_path, "w") as f:
                f.write(self.default_app_config)

        with open(app_config_path, "r") as f:
            return yaml.safe_load(f)

    @property
    def default_app_config(self):
        return """# Application configuration template
# All settings are optional - uncomment and modify as needed

# arguments passed to scrcpy
scrcpy_args: []
use_adb_keyboard: true
retrieve_app_icon: true
"""

    def save_app_config(self, app_name: str, config: Dict):
        app_config_path = self.get_app_config_path(app_name)
        with open(app_config_path, "w") as f:
            yaml.safe_dump(config, f)

    def list_all_apps(self) -> List[dict[str, str]]:
        # package_ids = self.swm.adb_wrapper.list_packages()
        package_list = self.swm.scrcpy_wrapper.list_package_id_and_alias()
        for it in package_list:
            package_id = it["id"]
            last_used_time = self.get_app_last_used_time_from_db(package_id)
            if last_used_time:
                it["last_used_time"] = last_used_time
            else:
                it["last_used_time"] = -1
        return package_list

    def list_most_used_apps(self, limit: int) -> List[dict[str, str]]:
        # Placeholder implementation
        all_apps = self.list_all_apps()
        all_apps.sort(key=lambda x: -x["last_used_time"])
        selected_apps = all_apps[:limit]
        return selected_apps


class SessionManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config
        self.session_dir = os.path.join(swm.cache_dir, "sessions")
        os.makedirs(self.session_dir, exist_ok=True)

    def search(self):
        sessions = self.list()
        return self.swm.fzf_wrapper.select_item(sessions)

    def list(self) -> List[str]:
        sessions = [f for f in os.listdir(self.session_dir) if f.endswith(".json")]
        return sessions

    def save(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")

        # Get current window positions and app states
        session_data = {
            "timestamp": time.time(),
            "device": self.swm.current_device,
            "windows": self._get_window_states(),
        }

        with open(session_path, "w") as f:
            json.dump(session_data, f, indent=2)

    def restore(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")

        if not os.path.exists(session_path):
            raise FileNotFoundError(f"Session not found: {session_name}")

        with open(session_path, "r") as f:
            session_data = json.load(f)

        # Restore each window
        for app_name, window_config in session_data["windows"].items():
            self.swm.app_manager.run(app_name)
            # Additional window positioning would go here

    def delete(self, session_name: str) -> bool:
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        if os.path.exists(session_path):
            os.remove(session_path)
            return True
        return False

    def _get_window_states(self) -> Dict:
        # Placeholder implementation
        return {}


class DeviceManager:
    def __init__(self, swm: SWM):
        self.swm = swm

    def list(self, print_formatted):
        ret = self.swm.adb_wrapper.devices()
        if print_formatted:
            load_and_print_as_dataframe(ret)
        return ret
        # TODO: use adb to get device name:
        # adb shell settings get global device_name
        # adb shell getprop net.hostname
        # set device name:
        # adb shell settings put global device_name "NEW_NAME"
        # adb shell settings setprop net.hostname "NEW_NAME"

    def search(self):
        return self.swm.fzf_wrapper.select_item(self.list())

    def select(self, device_id: int):
        self.swm.set_current_device(device_id)

    def name(self, device_id: str, alias: str):
        self.swm.adb_wrapper.set_device_name(device_id, alias)


class AdbWrapper:
    def __init__(self, adb_path: str, config: omegaconf.DictConfig):
        self.adb_path = adb_path
        self.config = config
        self.device = config.get("device")

        self.initialize()

    def get_device_name(self, device_id):
        # self.set_device(device_id)
        output = self.check_output(
            ["shell", "settings", "get", "global", "device_name"], device_id=device_id
        ).strip()
        return output

    def set_device_name(self, device_id, name):
        # self.set_device(device_id)
        self.execute(
            ["shell", "settings", "put", "global", "device_name", "name"],
            device_id=device_id,
        )

    def online(self):
        return self.device in self.list_device_ids()

    def create_file_if_not_exists(self, remote_path: str):
        if not self.test_path_existance(remote_path):
            basedir = os.path.dirname(remote_path)
            self.create_dirs(basedir)
            self.touch(remote_path)

    def touch(self, remote_path: str):
        self.execute(["shell", "touch", remote_path])

    def initialize(self):
        if self.online():
            self.create_swm_dir()

    def test_path_existance(self, remote_path: str):
        cmd = ["shell", "test", "-e", remote_path]
        result = self.execute(cmd, check=False)
        if result.returncode == 0:
            return True
        return False

    def set_device(self, device_id: str):
        self.device = device_id
        self.initialize()

    def _build_cmd(self, args: List[str], device_id=None) -> List[str]:
        cmd = [self.adb_path]
        if device_id:
            cmd.extend(["-s", device_id])
        elif self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd

    def execute(
        self,
        args: List[str],
        capture: bool = False,
        text=True,
        check=True,
        device_id=None,
    ) -> subprocess.CompletedProcess:
        cmd = self._build_cmd(args, device_id)
        result = subprocess.run(cmd, capture_output=capture, text=text, check=check)
        return result

    def check_output(self, args: List[str], device_id=None) -> str:
        return self.execute(args, capture=True, device_id=device_id).stdout.strip()

    def read_file(self, remote_path: str) -> str:
        """Read a remote file's content as a string."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            self.pull_file(remote_path, tmp_path)
            with open(tmp_path, "r") as f:
                return f.read()
        finally:
            os.unlink(tmp_path)

    def write_file(self, remote_path: str, content: str):
        """Write a string to a remote file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(content)
        try:
            self.push_file(tmp_path, remote_path)
        finally:
            os.unlink(tmp_path)

    def pull_file(self, remote_path: str, local_path: str):
        """Pull a file from the device to a local path."""
        self.execute(["pull", remote_path, local_path])

    def push_file(self, local_path: str, remote_path: str):
        """Push a local file to the device."""
        self.execute(["push", local_path, remote_path])

    def install_apk(self, apk_path: str):
        """Install an APK file on the device."""
        self.execute(["install", apk_path])

    def execute_java_code(java_code):
        # https://github.com/zhanghai/BeeShell
        # adb install --instant app.apk
        # adb shell pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so
        ...

    def retrieve_app_icon(self, app_id: str): ...

    def get_android_version(self) -> str:
        return self.check_output(["shell", "getprop", "ro.build.version.release"])

    def get_device_architecture(self) -> str:
        return self.check_output(["shell", "getprop", "ro.product.cpu.abi"])

    def list_device_ids(
        self, skip_unauthorized: bool = True, with_status: bool = False
    ) -> List[str]:

        # TODO: detect and filter unauthorized and abnormal devices
        output = self.check_output(["devices"])
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                elements = line.split()
                device_id = elements[0]
                device_status = elements[1]
                if not skip_unauthorized or device_status != "unauthorized":
                    if with_status:
                        devices.append({"id": device_id, "status": device_status})
                    else:
                        devices.append(device_id)
                else:
                    print("Warning: device %s unauthorized thus skipped" % device_id)
        return devices

    def list_device_detailed(self) -> List[str]:
        device_infos = self.list_device_ids(with_status=True)
        for it in device_infos:
            device_id = it["id"]
            device_name = self.get_device_name(device_id)
            it["name"] = device_name
        return device_infos

    def list_packages(self) -> List[str]:
        output = self.check_output(["shell", "pm", "list", "packages"])
        packages = []
        for line in output.splitlines():
            if line.startswith("package:"):
                packages.append(line[len("package:") :].strip())
        return packages

    def create_swm_dir(self):
        swm_dir = self.config.android_session_storage_path
        if self.test_path_existance(swm_dir):
            return
        print("On device SWM directory not found, creating it now...")
        self.create_dirs(swm_dir)

    def create_dirs(self, dirpath: str):
        self.execute(["shell", "mkdir", "-p", dirpath])

    def push_aapt(self, device_path: str = None):
        if device_path is None:
            device_path = os.path.join(self.config.android_session_storage_path, "aapt")
        device_architecture = self.get_device_architecture()
        local_aapt_path = os.path.join(
            self.config.cache_dir, "bin", "aapt-%s" % device_architecture
        )
        self.execute(["push", local_aapt_path, device_path])
        self.execute(["shell", "chmod", "755", device_path])

    def pull_session(self, session_name: str, local_path: str):
        remote_path = os.path.join(
            self.config.android_session_storage_path, session_name
        )
        self.execute(["pull", remote_path, local_path])


class ScrcpyWrapper:
    def __init__(self, scrcpy_path: str, config: omegaconf.DictConfig):
        self.scrcpy_path = scrcpy_path
        self.config = config
        self.device = config.get("device")

    # TODO: use "scrcpy --list-apps" instead of using aapt to parse app labels

    def list_package_id_and_alias(self):
        # scrcpy --list-apps
        output = self.check_output(["--list-apps"])
        # now, parse these apps
        parseable_lines = []
        for line in output.splitlines():
            # line: "package_id alias"
            line = line.strip()
            if line.startswith("* "):
                # system app
                parseable_lines.append(line)
            elif line.startswith("- "):
                # user app
                parseable_lines.append(line)
            else:
                # skip this line
                ...
        ret = []
        for it in parseable_lines:
            result = parse_scrcpy_app_list_output_single_line(it)
            ret.append(result)
        return ret

    def build_window_title_args(self, device_name: str, app_name: str):
        # TODO: set window title as "<device_name> - <app_name>"
        # --window-title=<title>
        return ["--window-title", "%s - %s" % (device_name, app_name)]

    def set_device(self, device_id: str):
        self.device = device_id

    def _build_cmd(self, args: List[str]) -> List[str]:
        cmd = [self.scrcpy_path]
        if self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd

    def execute(self, args: List[str]):
        cmd = self._build_cmd(args)
        subprocess.run(cmd, check=True)

    def execute_detached(self, args: List[str]):
        cmd = self._build_cmd(args)
        spawn_and_detach_process(cmd)

    def check_output(self, args: List[str]) -> str:
        cmd = self._build_cmd(args)
        output = subprocess.check_output(cmd).decode("utf-8")
        return output

    def launch_app(
        self,
        package_name: str,
        window_params: Dict = None,
        scrcpy_args: list[str] = None,
    ):
        args = []

        configured_window_options = []

        zoom_factor = self.config.zoom_factor  # TODO: make use of it

        if window_params:
            for it in ["x", "y", "width", "height"]:
                if it in window_params:
                    args.extend(["--window-%s=%s" % (it, window_params[it])])
                    configured_window_options.append("--window-%s" % it)

        if scrcpy_args:
            for it in scrcpy_args:
                if it.split("=")[0] not in configured_window_options:
                    args.append(it)
                else:
                    print(
                        "Warning: one of scrcpy options '%s' is already configured via window options"
                        % it
                    )

        args.extend(["--start-app", package_name])

        self.execute_detached(args)


class FzfWrapper:
    def __init__(self, fzf_path: str):
        self.fzf_path = fzf_path

    def select_item(self, items: List[str]) -> str:
        with tempfile.NamedTemporaryFile(mode="w+") as tmp:
            tmp.write("\n".join(items))
            tmp.flush()

            cmd = [self.fzf_path, "--layout=reverse"]
            result = subprocess.run(
                cmd, stdin=open(tmp.name, "r"), stdout=subprocess.PIPE, text=True
            )
            if result.returncode == 0:
                ret = result.stdout.strip()
            else:
                print("Error: fzf exited with code %d" % result.returncode)
                ret = ""
            print("FZF selection:", ret)
            return ret


def create_default_config(cache_dir: str) -> omegaconf.DictConfig:
    return omegaconf.OmegaConf.create(
        {
            "cache_dir": cache_dir,
            "device": None,
            "zoom_factor": 1.0,
            "db_path": os.path.join(cache_dir, "apps.db"),
            "session_autosave": True,
            "android_session_storage_path": "/sdcard/.swm",
            "github_mirrors": [
                "https://github.com",
                "https://bgithub.xyz",
                "https://kgithub.com",
            ],
            "binaries": {
                "adb": {"version": "1.0.41"},
                "scrcpy": {"version": "2.0"},
                "fzf": {"version": "0.42.0"},
            },
        }
    )


def get_config_path(cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    config_path = os.path.join(cache_dir, "config.yaml")
    return config_path


def load_or_create_config(cache_dir: str, config_path: str) -> omegaconf.DictConfig:
    if os.path.exists(config_path):
        print("Loading existing config from:", config_path)
        return omegaconf.OmegaConf.load(config_path)

    print("Creating default config at:", config_path)
    config = create_default_config(cache_dir)
    omegaconf.OmegaConf.save(config, config_path)
    return config


def override_system_excepthook(
    program_specific_params: Dict, ignorable_exceptions: list
):
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        if exc_type not in ignorable_exceptions:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, file=sys.stderr
            )
            print("\nAn unhandled exception occurred, showing diagnostic info:")
            print_diagnostic_info(program_specific_params)

    sys.excepthook = custom_excepthook


def parse_args():
    return docopt(__doc__, version=f"SWM {__version__}", options_first=True)


def main():
    # Setup cache directory
    default_cache_dir = os.path.expanduser("~/.swm")

    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", default_cache_dir)

    os.makedirs(SWM_CACHE_DIR, exist_ok=True)
    # Parse CLI arguments
    args = parse_args()

    config_path = args.get("--config")
    if config_path:
        print("Using CLI given config path:", config_path)
    else:
        config_path = get_config_path(SWM_CACHE_DIR)
    # Load or create config
    config = load_or_create_config(SWM_CACHE_DIR, config_path)

    verbose = args["--verbose"]
    debug = args["--debug"]

    # Prepare diagnostic info
    program_specific_params = {
        "cache_dir": SWM_CACHE_DIR,
        "config": omegaconf.OmegaConf.to_container(config),
        "config_path": config_path,
        "argv": sys.argv,
        "parsed_args": args,
        "executable": sys.executable,
        "config_overriden_parameters": {},
        "verbose": verbose,
    }

    if verbose:
        print("Verbose mode on. Showing diagnostic info:")
        print_diagnostic_info(program_specific_params)
    override_system_excepthook(
        program_specific_params=program_specific_params,
        ignorable_exceptions=(
            [] if debug else [NoDeviceError, NoSelectionError, NoBaseConfigError]
        ),
    )

    config.verbose = verbose
    config.debug = debug

    # Initialize SWM core
    swm = SWM(config)

    # # Command routing
    # try:
    if args["adb"]:
        execute_subprogram(swm.adb, args["<adb_args>"])

    elif args["scrcpy"]:
        execute_subprogram(swm.scrcpy, args["<scrcpy_args>"])

    elif args["baseconfig"]:
        if args["show"]:
            if args["diagnostic"]:
                print_diagnostic_info(program_specific_params)
            else:
                print(omegaconf.OmegaConf.to_yaml(config))

        elif args["edit"]:
            # Implementation would open editor
            print("Opening config editor")
            edit_or_open_file(config_path)

    elif args["device"]:
        if args["list"]:
            devices = swm.device_manager.list()
            print("\n".join(devices))
        elif args["search"]:
            device = swm.device_manager.search()
            ans = input("Choose an option(select|name):")
            if ans.lower() == "select":
                swm.device_manager.select(device)
            elif ans.lower() == "name":
                alias = input("Enter the alias for device %s:" % device)
                swm.device_manager.name(device, alias)
        elif args["select"]:
            swm.device_manager.select(args["<device_id>"])
        elif args["name"]:
            swm.device_manager.name(args["<device_id>"], args["<device_alias>"])

    elif args["--version"]:
        print(f"SWM version {__version__}")
    else:
        # Device specific branches

        # Handle device selection
        cli_device = args["--device"]
        config_device = config.device

        if cli_device is not None:
            default_device = cli_device
        else:
            default_device = config_device

        current_device = swm.infer_current_device(default_device)

        if current_device is not None:
            swm.set_current_device(current_device)
            swm.load_swm_on_device_db()
        else:
            raise NoDeviceError("No available device")

        if args["app"]:
            if args["list"]:
                apps = swm.app_manager.list(
                    print_formatted=True,
                    additional_fields=dict(
                        last_used_time=args["last_used"], type_symbol=args["type"]
                    ),
                )
            elif args["search"]:
                app_id = swm.app_manager.search(index=args["index"])
                if app_id is None:
                    raise NoSelectionError("No app has been selected")
                print("Selected app: {}".format(app_id))
                ans = prompt_for_option_selection(
                    ["run", "config"], "Please select an action:"
                )
                if ans.lower() == "run":
                    scrcpy_args = input("Application arguments:")
                    swm.app_manager.run(app_id, scrcpy_args)
                elif ans.lower() == "config":
                    opt = input("Please choose an option (edit|show)")
                    if opt == "edit":
                        swm.app_manager.edit_app_config(app_id)
                    elif opt == "show":
                        swm.app_manager.show_app_config(app_id)
            elif args["most-used"]:
                swm.app_manager.list(
                    most_used=args.get("<count>", 10), print_formatted=True
                )
            elif args["run"]:
                swm.app_manager.run(args["<app_name>"], args["<scrcpy_args>"])

            elif args["config"]:
                app_name = args["<app_name>"]
                if args["show"]:
                    swm.app_manager.show_app_config(app_name)
                elif args["edit"]:
                    swm.app_manager.edit_app_config(app_name)

        elif args["session"]:
            if args["list"]:
                sessions = swm.session_manager.list()
                print("\n".join(sessions))
            elif args["search"]:
                session_name = swm.session_manager.search()
                opt = input("Please specify an action (restore|delete)")
                if opt == "restore":
                    swm.session_manager.restore(session_name)
                elif opt == "delete":
                    swm.session_manager.delete(session_name)

            elif args["save"]:
                swm.session_manager.save(args["<session_name>"])

            elif args["restore"]:
                session_name = args.get("<session_name>", "default")
                swm.session_manager.restore(session_name)

            elif args["delete"]:
                swm.session_manager.delete(args["<session_name>"])
            else:
                ...  # Implement other device specific commands

    # except Exception as e:
    #     print(f"Error: {e}")
    #     if args["--verbose"]:
    #         traceback.print_exc()


if __name__ == "__main__":
    main()
