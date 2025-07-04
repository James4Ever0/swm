"""SWM - Scrcpy Window Manager

Usage:
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <query> [no-new-display] [<init_config>]
  swm [options] app list [last_used] [type] [latest]
  swm [options] app search [type] [index]
  swm [options] app most-used [<count>]
  swm [options] app config show-default
  swm [options] app config (show|edit) <config_name>
  swm [options] app config copy <source_name> <target_name>
  swm [options] session list [last_used]
  swm [options] session search [index]
  swm [options] session restore [session_name]
  swm [options] session delete <query>
  swm [options] session edit <query>
  swm [options] session save <session_name>
  swm [options] session copy <source> <target>
  swm [options] device list [last_used]
  swm [options] device search [index]
  swm [options] device select <query>
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

# TODO: only import package when needed

import os
import platform
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

import omegaconf
from tinydb import Query, Storage, TinyDB
from tinydb.table import Document

__version__ = "0.1.0"


def convert_unicode_escape(input_str):
    # Extract the hex part after 'u+'
    hex_str = input_str[2:]
    # Convert hex string to integer and then to Unicode character
    return chr(int(hex_str, 16))


def split_args(args_str: str):
    splited_args = args_str.split()
    ret = []
    for it in splited_args:
        it = it.strip()
        if it:
            ret.append(it)
    return ret


def encode_base64_str(data: str):
    import base64
    encoded_bytes = base64.b64encode(data.encode("utf-8"))
    encoded_str = encoded_bytes.decode("utf-8")
    return encoded_str


# TODO: use logger
# import structlog
# import loguru

# TODO: init app with named config

# TODO: put manual configuration into first priority, and we should only take care of those would not be manually done (like unicode input)
# TODO: create github pages for swm

# TODO: Create an app config template repo, along with all other devices, pcs, for easy initialization

# TODO: override icon with SCRCPY_ICON_PATH=<app_icon_path>

# TODO: not allowing exiting the app in the new display, or close the display if the app is exited, or reopen the app if exited

# TODO: configure app with the same id to use the same app config or separate by device

# TODO: write wiki about enabling com.android.shell for root access in kernelsu/magisk
# TODO: use a special apk for running SWM specific root commands instead of direct invocation of adb root shell

# TODO: monitor the output of scrcpy and capture unicode char input accordingly, for sending unicode char to the adbkeyboard


class NoDeviceError(ValueError): ...


class NoSelectionError(ValueError): ...


class NoConfigError(ValueError): ...


class NoAppError(ValueError): ...


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
    import shutil
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


def get_file_content(filepath: str):
    with open(filepath, "r") as f:
        return f.read()


def edit_or_open_file(filepath: str, return_value="edited"):
    print("Editing file:", filepath)
    content_before_edit = get_file_content(filepath)
    editor_binpath = select_editor()
    if editor_binpath:
        edit_file(filepath, editor_binpath)
    else:
        open_file_with_default_application(filepath)
    content_after_edit = get_file_content(filepath)
    edited = content_before_edit != content_after_edit
    if edited:
        print("File has been edited.")
    else:
        print("File has not been edited.")
    if return_value == "edited":
        return edited
    elif return_value == "content":
        return content_after_edit
    else:
        raise ValueError("Unknown return value:", return_value)


def open_file_with_default_application(filepath: str):
    import shutil
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
    import tempfile
    import requests
    import zipfile
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
    import json
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
    import shutil
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
        import json
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
        import json
        content = json.dumps(data)
        self.adb_wrapper.write_file(self.filename, content)
        if self.enable_read_cache:
            self.read_cache = content

    def close(self):
        pass


class SWMOnDeviceDatabase:
    def __init__(self, db_path: str, adb_wrapper: "AdbWrapper"):
        import functools
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

    def get_app_last_used_time(self, device_id, app_id: str) -> Optional[datetime]:
        AppUsage = Query()

        # Search for matching document
        result = self._db.table("app_usage").get(
            (AppUsage.device_id == device_id) & (AppUsage.app_id == app_id)
        )
        # Return datetime object if found, None otherwise

        if result:
            assert type(result) == Document
            return datetime.fromisoformat(result["last_used_time"])


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
        self.scrcpy_wrapper = ScrcpyWrapper(self.scrcpy, self.config, self.adb_wrapper)
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
            if default_device is None:
                print(
                    "No device is specified in config, using the only device online (%s)"
                    % device
                )
            elif device != default_device:
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
                if default_device is None:
                    print("No device is specified in config, please select one.")
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
    import pandas

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

    def resolve_app_main_activity(self, app_id: str):
        # adb shell cmd package resolve-activity --brief <PACKAGE_NAME> | tail -n 1
        ...

    def start_app_in_given_display(self, app_id: str, display_id: int):
        # adb shell am start --display <DISPLAY_ID> -n <PACKAGE/ACTIVITY>
        ...

    def resolve_app_query(self, query: str):
        print("Warning: app query resolution not implemented")
        return query

    # let's mark it rooted device only.
    # we get the package path, data path and get last modification date of these files
    # or use java to access UsageStats
    def get_app_last_used_time_from_device(self):
        cmd = ""
        last_used_time = self.swm.adb_wrapper.execute_su_cmd(cmd, capture=True)
        return last_used_time

    def get_app_last_used_time_from_db(self, package_id: str):
        assert self.swm.on_device_db
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
        update_cache=False,
        additional_fields: dict = {},
    ):

        if most_used:
            apps = self.list_most_used_apps(most_used, update_cache=update_cache)
        else:
            apps = self.list_all_apps(update_cache=update_cache)

        if print_formatted:
            load_and_print_as_dataframe(apps, additional_fields=additional_fields)

        return apps

    def install_and_use_adb_keyboard(self):  # require root
        # TODO: check root avalibility, decorate this method, if no root is found then raise exception
        self.swm.adb_wrapper.install_adb_keyboard()
        self.swm.adb_wrapper.execute_su_cmd(
            "ime enable com.android.adbkeyboard/.AdbIME"
        )
        self.swm.adb_wrapper.execute_su_cmd("ime set com.android.adbkeyboard/.AdbIME")

    def retrieve_app_icon(self, package_id: str, icon_path: str):
        self.swm.adb_wrapper.retrieve_app_icon(package_id, icon_path)

    def build_window_title(self, package_id: str):
        # TODO: set window title as "<device_name> - <app_name>"
        # --window-title=<title>
        device_id = self.swm.adb_wrapper.device
        device_name = self.swm.adb_wrapper.get_device_name(device_id)
        app_name = package_id
        # app_name = self.swm.adb_wrapper.get_app_name(package_id)
        return "%s - %s" % (app_name, device_name)

    def check_app_existance(self, app_id):
        return self.swm.adb_wrapper.check_app_existance(app_id)

    def run(
        self, app_id: str, init_config: Optional[str] = None, new_display: bool = True
    ):

        if not self.check_app_existance(app_id):
            raise NoAppError(
                "Applicaion %s does not exist on device %s"
                % (app_id, self.swm.current_device)
            )
        # TODO: memorize the last scrcpy run args, by default in swm config
        # Get app config
        env = {}
        app_config = self.get_or_create_app_config(app_id)
        use_adb_keyboard = app_config.get("use_adb_keyboard", False)
        if use_adb_keyboard:
            self.install_and_use_adb_keyboard()

        if app_config.get("retrieve_app_icon", False):
            print("[Warning] Retrieving app icon is not implemented yet")
            # icon_path = os.path.join(self.swm.config_dir, "icons", "%s.png" % app_id)
            # if not os.path.exists(icon_path):
            #     self.retrieve_app_icon(app_id, icon_path)
            #     env["SCRCPY_ICON_PATH"] = icon_path
        # Add window config if exists
        win = app_config.get("window", None)

        scrcpy_args = []

        # if scrcpy_args is None:
        #     scrcpy_args = app_config.get("scrcpy_args", None)

        title = self.build_window_title(app_id)

        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(
            app_id,
            window_params=win,
            scrcpy_args=scrcpy_args,
            title=title,
            new_display=new_display,
            use_adb_keyboard=use_adb_keyboard,
            env=env,
        )

    def edit_app_config(self, app_name: str) -> bool:
        # return True if edited, else False
        print(f"Editing config for {app_name}")
        app_config_path = self.get_app_config_path(app_name)
        self.get_or_create_app_config(app_name)
        ret = edit_or_open_file(app_config_path)
        assert type(ret) == bool
        return ret

    def show_app_config(self, app_name: str):
        config = self.get_or_create_app_config(app_name)
        print(pretty_print_json(config))

    def get_app_config_path(self, app_name: str):

        app_config_dir = os.path.join(self.swm.cache_dir, "apps")
        os.makedirs(app_config_dir, exist_ok=True)

        app_config_path = os.path.join(app_config_dir, f"{app_name}.yaml")
        return app_config_path

    def get_or_create_app_config(self, app_name: str) -> Dict:
        import yaml
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

    def list_all_apps(self, update_cache=False) -> List[dict[str, str]]:
        # package_ids = self.swm.adb_wrapper.list_packages()
        package_list, cache_expired = (
            self.swm.scrcpy_wrapper.load_package_id_and_alias_cache()
        )
        if update_cache or cache_expired:
            package_list = self.swm.scrcpy_wrapper.list_package_id_and_alias()
            self.swm.scrcpy_wrapper.save_package_id_and_alias_cache(package_list)
        assert type(package_list) == list

        for it in package_list:
            package_id = it["id"]
            last_used_time = self.get_app_last_used_time_from_db(package_id)
            if last_used_time:
                it["last_used_time"] = last_used_time.timestamp()
            else:
                it["last_used_time"] = -1
        return package_list

    def list_most_used_apps(
        self, limit: int, update_cache=False
    ) -> List[dict[str, Any]]:
        # Placeholder implementation
        all_apps = self.list_all_apps(update_cache=update_cache)
        all_apps.sort(key=lambda x: -x["last_used_time"])  # type: ignore
        selected_apps = all_apps[:limit]
        return selected_apps


# TODO: manual specification instead of automatic
# TODO: specify pc display size in session config
class SessionManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.adb_wrapper = swm.adb_wrapper
        self.config = swm.config
        self.session_dir = os.path.join(
            swm.config.android_session_storage_path, "sessions"
        )  # remote path
        self.swm.adb_wrapper.execute(
            ["shell", "mkdir", "-p", self.session_dir], check=False
        )

    @property
    def template_session_config(self):
        return ""

    def resolve_session_query(self, query):
        print("Warning: query resolution not implemented")
        return query

    def get_swm_window_params(self) -> List[Dict[str, Any]]:
        windows = self.get_all_window_params()
        windows = [it for it in windows if it["title"].startswith("[SWM]")]
        return windows

    def get_all_window_params(self) -> List[Dict[str, Any]]:
        os_type = platform.system()
        if os_type == "Linux":
            if not self._is_wmctrl_installed():
                print("Please install wmctrl to manage windows on Linux.")
                return []
            return self._get_windows_linux()
        elif os_type == "Windows":
            return self._get_windows_windows()
        elif os_type == "Darwin":
            return self._get_windows_macos()
        else:
            print(f"Unsupported OS: {os_type}")
            return []

    def _is_wmctrl_installed(self) -> bool:
        try:
            subprocess.run(
                ["wmctrl", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _get_windows_linux(self) -> List[Dict[str, Any]]:
        try:
            output = subprocess.check_output(["wmctrl", "-lGx"]).decode("utf-8")
            windows = []
            for line in output.splitlines():
                parts = line.split(maxsplit=6)
                if len(parts) < 7:
                    continue
                desktop_id = parts[1]
                pid = parts[2]
                x, y, width, height = map(int, parts[3:7])
                title = parts[6]
                windows.append(
                    {
                        "title": title,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "desktop_id": desktop_id,
                        "pid": pid,
                    }
                )
            return windows
        except Exception as e:
            print(f"Error getting windows on Linux: {e}")
            return []

    def _get_windows_windows(self) -> List[Dict[str, Any]]:
        try:
            import pygetwindow as gw

            windows = []
            for win in gw.getAllWindows():
                title = win.title
                windows.append(
                    {
                        "title": title,
                        "x": win.left,
                        "y": win.top,
                        "width": win.width,
                        "height": win.height,
                        "is_maximized": win.isMaximized,
                        "hwnd": win._hWnd,
                    }
                )
            return windows
        except ImportError:
            print("Please install pygetwindow: pip install pygetwindow")
            return []
        except Exception as e:
            print(f"Error getting windows on Windows: {e}")
            return []

    def _get_windows_macos(self) -> List[Dict[str, Any]]:
        try:
            from AppKit import NSWorkspace

            windows = []
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.isActive():
                    app_name = app.localizedName()
                    windows.append({"title": app_name, "pid": app.processIdentifier()})
            return windows
        except ImportError:
            print("macOS support requires PyObjC. Install with: pip install pyobjc")
            return []
        except Exception as e:
            print(f"Error getting windows on macOS: {e}")
            return []

    def move_window_to_position(self, window_title: str, window_params: Dict[str, Any]):
        os_type = platform.system()
        if os_type == "Linux":
            self._move_window_linux(window_title, window_params)
        elif os_type == "Windows":
            self._move_window_windows(window_title, window_params)
        elif os_type == "Darwin":
            self._move_window_macos(window_title, window_params)
        else:
            print(f"Unsupported OS: {os_type}")

    def _move_window_linux(self, window_title: str, window_params: Dict[str, Any]):
        if not self._is_wmctrl_installed():
            print("wmctrl not installed. Cannot move window.")
            return
        try:
            x = window_params.get("x", 0)
            y = window_params.get("y", 0)
            width = window_params.get("width", 800)
            height = window_params.get("height", 600)
            desktop_id = window_params.get("desktop_id", "0")
            cmd = f"wmctrl -r '{window_title}' -e '0,{x},{y},{width},{height}'"
            if desktop_id:
                cmd += f" -t {desktop_id}"
            subprocess.run(cmd, shell=True, check=True)
        except Exception as e:
            print(f"Error moving window on Linux: {e}")

    def _move_window_windows(self, window_title: str, window_params: Dict[str, Any]):
        try:
            import pygetwindow as gw

            wins = gw.getWindowsWithTitle(window_title)
            if wins:
                win = wins[0]
                if win.isMaximized:
                    win.restore()
                win.resizeTo(
                    window_params.get("width", 800), window_params.get("height", 600)
                )
                win.moveTo(window_params.get("x", 0), window_params.get("y", 0))
        except ImportError:
            print("Please install pygetwindow: pip install pygetwindow")
        except Exception as e:
            print(f"Error moving window on Windows: {e}")

    def _move_window_macos(self, window_title: str, window_params: Dict[str, Any]):
        try:
            from AppKit import NSWorkspace

            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.localizedName() == window_title:
                    app.activateWithOptions_(NSWorkspaceLaunchDefault)
                    break
            print(
                "Note: Detailed window moving on macOS is complex and not fully implemented here."
            )
        except ImportError:
            print("macOS support requires PyObjC. Install with: pip install pyobjc")
        except Exception as e:
            print(f"Error moving window on macOS: {e}")

    def get_pc_screen_size(self) -> Optional[Dict[str, int]]:
        os_type = platform.system()
        if os_type == "Linux":
            try:
                output = subprocess.check_output(["xrandr", "--query"]).decode("utf-8")
                for line in output.splitlines():
                    if "*+" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if "+" in part and "x" in part:
                                width, height = part.split("x")
                                return {"width": int(width), "height": int(height)}
            except Exception as e:
                print(f"Error getting screen size on Linux: {e}")
        elif os_type == "Windows":
            try:
                import win32api

                width = win32api.GetSystemMetrics(0)
                height = win32api.GetSystemMetrics(1)
                return {"width": width, "height": height}
            except ImportError:
                print("win32api not available. Install pywin32.")
            except Exception as e:
                print(f"Error getting screen size on Windows: {e}")
        elif os_type == "Darwin":
            try:
                from AppKit import NSScreen

                screen = NSScreen.mainScreen().frame().size
                return {"width": int(screen.width), "height": int(screen.height)}
            except ImportError:
                print("macOS support requires PyObjC. Install with: pip install pyobjc")
            except Exception as e:
                print(f"Error getting screen size on macOS: {e}")
        else:
            print(f"Unsupported OS: {os_type}")
        return None

    def search(self):
        sessions = self.list()
        return self.swm.fzf_wrapper.select_item(sessions)

    def list(self) -> List[str]:
        sessions = [f for f in os.listdir(self.session_dir) if f.endswith(".json")]
        return sessions

    def save(self, session_name: str):
        import time

        # Get current window positions and app states
        session_data = {
            "timestamp": time.time(),
            "device": self.swm.current_device,
            "windows": self._get_window_states(),
        }

        self._save_session_data(session_name, session_data)

    def exists(self, session_name: str) -> bool:
        session_path = self.get_session_path(session_name)
        return self.adb_wrapper.test_path_existance(session_path)

    def copy(self, source, target):
        sourcepath = self.get_session_path(source)
        targetpath = self.get_session_path(target)
        assert self.adb_wrapper.test_path_existance(sourcepath)
        assert not self.adb_wrapper.test_path_existance(targetpath)
        self.adb_wrapper.execute(["shell", "cp", sourcepath, targetpath])

    def edit(self, session_name: str):
        import tempfile
        session_path = self.get_session_path(session_name)
        if self.adb_wrapper.test_path_existance(session_name):
            tmpfile_content = self.adb_wrapper.read_file(session_path)
        else:
            tmpfile_content = self.template_session_config

        with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
            tmpfile.write(tmpfile_content)
            tmpfile.flush()
            edited_content = edit_or_open_file(tmpfile.name, return_value="content")
            assert type(edited_content) == str
            self.swm.adb_wrapper.write_file(session_path, edited_content)

    def get_session_path(self, session_name):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        return session_path

    def _save_session_data(self, session_name, session_data):
        import json
        session_path = self.get_session_path(session_name)
        content = json.dumps(session_data, indent=2)
        self.swm.adb_wrapper.write_file(session_path, content)

    def restore(self, session_name: str):
        import json
        session_path = os.path.join(self.session_dir, f"{session_name}.json")

        if not self.swm.adb_wrapper.test_path_existance(session_path):
            raise FileNotFoundError(f"Session not found: {session_name}")

        content = self.swm.adb_wrapper.read_file(session_path)
        session_data = json.loads(content)

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
        ret = self.swm.adb_wrapper.list_device_detailed()
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
        return self.swm.fzf_wrapper.select_item(self.list(print_formatted=False))

    def select(self, device_id: str):
        self.swm.set_current_device(device_id)

    def name(self, device_id: str, alias: str):
        self.swm.adb_wrapper.set_device_name(device_id, alias)


class AdbWrapper:
    def __init__(self, adb_path: str, config: omegaconf.DictConfig):
        self.adb_path = adb_path
        self.config = config
        self.device = config.get("device")
        self.remote_swm_dir = self.config.android_session_storage_path
        self.initialize()
        self.remote = self

    def check_has_root(self):
        return self.execute_su_cmd("whoami", check=False).returncode == 0

    def get_current_ime(self):
        # does not require su, but anyway we just use su
        output = self.check_output_su("settings get secure default_input_method")
        return output

    def list_active_imes(self):
        return self.check_output_su("ime list -s").splitlines()

    def set_current_ime(self, ime_name):
        self.execute_su_cmd(f"settings put secure default_input_method {ime_name}")

    def check_output_su(self, cmd: str, **kwargs):
        return self.check_output(["su", "-c", cmd], **kwargs)

    def check_output_shell(self, cmd_args: list[str], **kwargs):
        return self.check_output(["shell"] + cmd_args, **kwargs)

    # TODO: if app is not foreground, or is ime input target but has different display id, then we close the corresponding scrcpy window

    def get_display_density(self, display_id):
        # adb shell wm density -d <display_id>
        output = self.check_output(["shell", "wm", "density", "-d", display_id])

    def get_display_current_focus(self):
        # adb shell dumpsys window | grep "ime" | grep display
        # adb shell dumpsys window displays | grep "mCurrentFocus"
        output = self.check_output(["shell", "dumpsys", "window", "displays"])
        # we can get display id and current focused app per display here
        # just need to parse section "WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)"

    def check_app_is_foreground(self, app_id):
        # convert the binary output from "wm dump-visible-window-views" into ascii byte by byte, those not viewable into "."
        # adb shell wm dump-visible-window-views | xxd | grep <app_id>

        # or use the readable output from dumpsys
        # adb shell "dumpsys activity activities | grep ResumedActivity" | grep <app_id>
        output = self.check_output(["shell", "dumpsys", "activity", "activities"])

    def check_app_existance(self, app_id):
        apk_path = self.get_app_apk_path(app_id)
        if apk_path:
            return True
        return False

    def check_if_screen_unlocked(self):
        output = self.check_output(["shell", "dumpsys", "power"])
        # reference: https://stackoverflow.com/questions/35275828/is-there-a-way-to-check-if-android-device-screen-is-locked-via-adb
        # adb shell dumpsys power | grep 'mHolding'
        # If both are false, the display is off.
        # If mHoldingWakeLockSuspendBlocker is false, and mHoldingDisplaySuspendBlocker is true, the display is on, but locked.
        # If both are true, the display is on.

    def adb_keyboard_input_text(self, text: str):
        # adb shell am broadcast -a ADB_INPUT_B64 --es msg `echo -n '你好' | base64`
        base64_text = encode_base64_str(text)
        self.execute_shell(
            ["am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", base64_text]
        )
        # TODO: restore the previously using keyboard after swm being detached, either manually or using script/apk
        ...

    def execute_shell(self, cmd_args: list[str], **kwargs):
        self.execute(["shell", *cmd_args], **kwargs)

    def get_device_name(self, device_id):
        # self.set_device(device_id)
        output = self.check_output(
            ["shell", "settings", "get", "global", "device_name"], device_id=device_id
        ).strip()
        return output

    def set_device_name(self, device_id, name):
        # self.set_device(device_id)
        self.execute_shell(
            ["settings", "put", "global", "device_name", name],
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
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            self.pull_file(remote_path, tmp_path)
            with open(tmp_path, "r") as f:
                return f.read()
        finally:
            os.unlink(tmp_path)

    def write_file(self, remote_path: str, content: str):
        import tempfile
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

    def get_swm_apk_path(self, apk_name: str) -> str:
        path = os.path.join(self.config.cache_dir, f"apk/{apk_name}.apk")
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"APK file {apk_name} not found in cache")

    def install_adb_keyboard(self):
        apk_path = self.get_swm_apk_path("ADBKeyboard")
        self.install_apk(apk_path)

    def execute_su_cmd(self, cmd: str, **kwargs):
        return self.execute(["shell", "su", "-c", cmd], **kwargs)

    def execute_su_script(self, script: str, **kwargs):
        tmpfile = "/sdcard/.swm/tmp.sh"
        self.write_file(tmpfile, script)
        cmd = "sh %s" % tmpfile
        return self.execute_su_cmd(cmd, **kwargs)

    def enable_adb_keyboard(self):
        self.execute(
            [
                "shell",
                "am",
                "start",
                "-n",
                "com.jb.gokeyboard/.activity.GoKeyboardActivity",
            ]
        )

    def disable_adb_keyboard(self):
        self.execute(["shell", "am", "force-stop", "com.jb.gokeyboard"])

    def install_apk(self, apk_path: str, instant=False):
        """Install an APK file on the device."""
        if os.path.exists(apk_path):
            cmd = ["install"]
            if instant:
                cmd.extend(["--instant"])
            cmd.append(apk_path)
            self.execute(cmd)
        else:
            raise FileNotFoundError(f"APK file not found: {apk_path}")

    def install_beeshell(self):
        apk_path = self.get_swm_apk_path("beeshell")
        self.install_apk(apk_path)

    def execute_java_code(self, java_code):
        # https://github.com/zhanghai/BeeShell
        # adb install --instant app.apk
        # adb shell pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so {tmp_path}

        """Execute Java code on the device."""
        self.install_beeshell()
        bsh_tmp_path = "/data/local/tmp/swm_java_code.bsh"
        sh_tmp_path = "/data/local/tmp/swm_java_code_runner.sh"
        java_code_runner = (
            "pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so "
            + bsh_tmp_path
        )
        self.write_file(bsh_tmp_path, java_code)
        self.write_file(sh_tmp_path, java_code_runner)

    def get_app_apk_path(self, app_id: str):
        output = self.check_output(["shell", "pm", "path", app_id]).strip()
        if output:
            prefix = "package:"
            apk_path = output[len(prefix) :]
            return apk_path

    def extract_app_icon(self, app_apk_remote_path: str, icon_remote_dir: str):
        zip_icon_path = ""
        extracted_icon_remote_path = os.path.join(icon_remote_dir, zip_icon_path)
        self.execute_shell(
            ["unzip", app_apk_remote_path, "-d", icon_remote_dir, zip_icon_path]
        )
        return extracted_icon_remote_path

    def retrieve_app_icon(self, app_id: str, local_icon_path: str):
        remote_icon_png_path = f"/sdcard/.swm/icons/{app_id}_icon.png"
        tmpdir = "/sdcard/.swm/tmp"
        if not self.test_path_existance(remote_icon_png_path):
            aapt_bin_path = self.install_aapt_binary()
            apk_remote_path = self.get_app_apk_path(app_id)
            assert apk_remote_path, f"cannot find apk path for {app_id}"
            icon_remote_dir = tmpdir
            icon_remote_raw_path = self.extract_app_icon(
                apk_remote_path, icon_remote_dir
            )
            icon_format = icon_remote_raw_path.lower().split(".")[-1]
            # TODO:
            # use self.remote.* for all remote operations
            if icon_format == "xml":
                self.convert_icon_xml_to_png(icon_remote_raw_path, remote_icon_png_path)
            elif icon_format == "png":
                self.copy_file(icon_remote_raw_path, remote_icon_png_path)
            elif icon_format == "webp":
                self.convert_webp_to_png(icon_remote_raw_path, remote_icon_png_path)
            else:
                raise Exception("Unknown icon format %s" % icon_format)
            self.remove_dir(tmpdir, confirm=False)
        self.pull_file(remote_icon_png_path, local_icon_path)

    def convert_icon_xml_to_png(self, icon_xml_path, icon_png_path):
        java_code = f"""input_icon_path = "{icon_xml_path}"
output_icon_path = "{icon_png_path}"
"""
        self.execute_java_code(java_code)

    def convert_webp_to_png(self, webp_path, png_path):
        java_code = f"""input_icon_path = "{webp_path}"
output_icon_path = "{png_path}"
"""
        self.execute_java_code(java_code)

    def copy_file(self, src_path, dst_path):
        self.execute_shell(["cp", src_path, dst_path])

    def remove_dir(self, dir_path, confirm=True):
        if confirm:
            ans = input("Are you sure you want to remove %s? (y/n)" % dir_path)
            if ans.lower() != "y":
                print("Aborting...")
                return
        self.execute(["rm", "-rf", dir_path])

    def install_aapt_binary(self):
        aapt_bin_path = os.path.join(self.remote_swm_dir, "aapt")
        if not self.test_path_existance(aapt_bin_path):
            self.push_aapt(aapt_bin_path)
        return aapt_bin_path

    def get_android_version(self) -> str:
        return self.check_output(["shell", "getprop", "ro.build.version.release"])

    def get_device_architecture(self) -> str:
        return self.check_output(["shell", "getprop", "ro.product.cpu.abi"])

    def list_device_ids(
        self, skip_unauthorized: bool = True, with_status: bool = False
    ) -> List:

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
        swm_dir = self.remote_swm_dir
        if self.test_path_existance(swm_dir):
            return
        print("On device SWM directory not found, creating it now...")
        self.create_dirs(swm_dir)

    def create_dirs(self, dirpath: str):
        self.execute(["shell", "mkdir", "-p", dirpath])

    def push_aapt(self, device_path: Optional[str] = None):
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
    def __init__(
        self, scrcpy_path: str, config: omegaconf.DictConfig, adb_wrapper: "AdbWrapper"
    ):
        self.scrcpy_path = scrcpy_path
        self.config = config
        self.device = config.get("device")
        self.adb_wrapper = adb_wrapper

    @property
    def app_list_cache_path(self):
        return os.path.join(
            self.config.android_session_storage_path, "package_list_cache.json"
        )

    def load_package_id_and_alias_cache(self):
        import json
        import time
        package_list = None
        cache_expired = True
        if self.adb_wrapper.test_path_existance(self.app_list_cache_path):
            content = self.adb_wrapper.read_file(self.app_list_cache_path)
            data = json.loads(content)
            cache_save_time = data["cache_save_time"]
            now = time.time()
            cache_age = now - cache_save_time
            if cache_age < self.config.app_list_cache_update_interval:
                cache_expired = False
                package_list = data["package_list"]
        return package_list, cache_expired

    def save_package_id_and_alias_cache(self, package_list):
        import json
        import time
        data = {"package_list": package_list, "cache_save_time": time.time()}
        content = json.dumps(data)
        self.adb_wrapper.write_file(self.app_list_cache_path, content)

    def get_active_display_ids(self):
        # scrcpy --list-displays
        output = self.check_output(["--list-displays"])
        output_lines = output.splitlines()
        ret = {}
        for it in output_lines:
            it = it.strip()
             # we can only have size here, not dpi
            if it.startswith("--display-id"):
                display_id_part, size_part = it.split()
                display_id = display_id_part.split("=")[-1]
                display_id = int(display_id)
                size_part = size_part.replace("(", "").replace(")", "")
                x_size, y_size = size_part.split("x")
                x_size, y_size = int(x_size), int(y_size)
                ret[display_id] = dict(x=x_size, y=y_size)
        return ret
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
        new_display=True,
        title: str = None,
        use_adb_keyboard=False,
        env={},
    ):
        import signal
        args = []

        configured_window_options = []

        zoom_factor = self.config.zoom_factor  # TODO: make use of it

        if window_params:
            for it in ["x", "y", "width", "height"]:
                if it in window_params:
                    args.extend(["--window-%s=%s" % (it, window_params[it])])
                    configured_window_options.append("--window-%s" % it)

        if new_display:
            args.extend(["--new-display"])

        if title:
            args.extend(["--window-title", title])

        if scrcpy_args:
            for it in scrcpy_args:
                if it.split("=")[0] not in configured_window_options:
                    args.append(it)
                else:
                    print(
                        "Warning: one of scrcpy options '%s' is already configured" % it
                    )

        args.extend(["--start-app", package_name])
        # reference: https://stackoverflow.com/questions/2804543/read-subprocess-stdout-line-by-line

        # self.execute_detached(args)
        # self.execute(args)
        unicode_char_warning = "[server] WARN: Could not inject char"
        cmd = self._build_cmd(args)
        proc = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True, env=env
        )
        proc_pid = proc.pid
        assert proc.stderr
        previous_ime = self.adb_wrapper.get_current_ime()
        # TODO: capture stdout for getting new display id
        # TODO: collect missing char into batches and execute once every 0.5 seconds
        # TODO: restart the app in given display if exited (configure this behavior as an option "on_app_exit")
        try:
            for line in proc.stderr:
                captured_line = line.strip()
                if self.config.verbose:
                    ...
                print(
                    "<scrcpy stderr> %s" % captured_line
                )  # now we check if this indicates some character we need to type in
                if captured_line.startswith(unicode_char_warning):
                    char_repr = captured_line[len(unicode_char_warning) :].strip()
                    char_str = convert_unicode_escape(char_repr)
                    # TODO: use clipboard set and paste instead
                    # TODO: make unicode_input_method a text based config, opening the main display to show the default input method interface when no clipboard input or adb keyboard is enabled
                    # TODO: hover the main display on the focused new window to show input candidates
                    # Note: gboard is useful for single display, but not good for multi display.
                    if use_adb_keyboard:
                        self.adb_wrapper.adb_keyboard_input_text(char_str)
                    else:
                        self.clipboard_paste_input_text(char_str)
                # [server] WARN: Could not inject char u+4f60
                # TODO: use adb keyboard for pasting text from clipboard
        finally:
            # TODO: close the app when the main process is closed
            # kill by pid
            os.kill(proc_pid, signal.SIGKILL)
            proc.kill()
            # TODO: revert back to previously using ime, if no other opening swm window
            # if self.swm.check_no_other_swm_running():
            # self.adb_wrapper.execute_su_cmd("ime enable %s" % previous_ime)

    def clipboard_paste_input_text(self, text: str):
        import pyperclip
        import pyautogui
        pyperclip.copy(text)
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")


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


def create_default_config(cache_dir: str):
    return omegaconf.OmegaConf.create(
        {
            "cache_dir": cache_dir,
            "device": None,  # TODO: not storing this value here, but upsert it to local tinydb
            "zoom_factor": 1.0,
            "db_path": os.path.join(cache_dir, "apps.db"),
            "session_autosave": True,
            "android_session_storage_path": "/sdcard/.swm",
            "app_list_cache_update_interval": 60 * 60 * 24,  # 1 day
            "session_autosave_interval": 60 * 60,  # 1 hour
            "app_list_cache_path": os.path.join(cache_dir, "app_list_cache.json"),
            "github_mirrors": [
                "https://github.com",
                "https://bgithub.xyz",
                "https://kgithub.com",
            ],
            "use_shared_app_config": True,
            "binaries": {
                "adb": {"version": "1.0.41"},
                "scrcpy": {"version": "2.0"},
                "fzf": {"version": "0.42.0"},
                "adbkeyboard": {"version": "1.0.0"},
                "beeshell": {"version": "1.0.0"},
                "aapt": {"version": "1.0.0"},
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
    import sys
    import traceback
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        if exc_type not in ignorable_exceptions:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, file=sys.stderr
            )
            print("\nAn unhandled exception occurred, showing diagnostic info:")
            print_diagnostic_info(program_specific_params)

    sys.excepthook = custom_excepthook


def parse_args():
    from docopt import docopt

    return docopt(__doc__, version=f"SWM {__version__}", options_first=True)


def main():
    import sys
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

    if debug:
        print(
            "Debug mode on. Overriding system excepthook to capture unhandled exceptions."
        )
        override_system_excepthook(
            program_specific_params=program_specific_params,
            ignorable_exceptions=(
                [] if verbose else [NoDeviceError, NoSelectionError, NoBaseConfigError]
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
            swm.device_manager.list(print_formatted=True)
        elif args["search"]:
            device = swm.device_manager.search()
            ans = prompt_for_option_selection(["select", "name"], "Choose an option:")
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
                update_cache = args[
                    "latest"
                ]  # cache previous list result (alias, id), but last_used_time is always up-to-date
                apps = swm.app_manager.list(
                    print_formatted=True,
                    update_cache=update_cache,
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
                    init_config = input("Initial config name:")
                    run_in_new_display = input("Run in new display? (y/n, default: y):")
                    if run_in_new_display.lower() == "n":
                        no_new_display = True
                    else:
                        no_new_display = False
                    swm.app_manager.run(app_id, init_config=init_config)
                elif ans.lower() == "config":
                    opt = prompt_for_option_selection(
                        ["edit", "show"], "Please choose an option:"
                    )
                    if opt == "edit":
                        swm.app_manager.edit_app_config(app_id)
                    elif opt == "show":
                        swm.app_manager.show_app_config(app_id)
            elif args["most-used"]:
                swm.app_manager.list(
                    most_used=args.get("<count>", 10), print_formatted=True
                )
            elif args["run"]:
                no_new_display = args["no-new-display"]
                query = args["<query>"]
                init_config = args["<init_config>"]
                # TODO: search with query instead
                app_id = swm.app_manager.resolve_app_query(query)
                swm.app_manager.run(
                    app_id,
                    init_config=init_config,
                    new_display=not no_new_display,
                )

            elif args["config"]:
                config_name = args["<config_name>"]
                if args["show"]:
                    swm.app_manager.show_app_config(config_name)
                elif args["edit"]:
                    swm.app_manager.edit_app_config(config_name)

        elif args["session"]:
            if args["list"]:
                sessions = swm.session_manager.list()
                print("\n".join(sessions))
            elif args["search"]:
                session_name = swm.session_manager.search()
                opt = prompt_for_option_selection(
                    ["restore", "delete"], "Please specify an action:"
                )
                if opt == "restore":
                    swm.session_manager.restore(session_name)
                elif opt == "delete":
                    swm.session_manager.delete(session_name)

            elif args["save"]:
                swm.session_manager.save(args["<session_name>"])

            elif args["restore"]:
                query = args["<query>"]
                if query is None:
                    query = "default"
                session_name = swm.session_manager.resolve_session_query(query)
                swm.session_manager.restore(session_name)

            elif args["delete"]:
                session_name = swm.session_manager.resolve_session_query(
                    args["<query>"]
                )
                swm.session_manager.delete(session_name)
            else:
                ...  # Implement other device specific commands

    # except Exception as e:
    #     print(f"Error: {e}")
    #     if args["--verbose"]:
    #         traceback.print_exc()


if __name__ == "__main__":
    main()
