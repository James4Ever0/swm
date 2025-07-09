__doc__ = (
    DOCSTRING
) = """SWM - Scrcpy Window Manager

Usage:
  swm init
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <query> [no-new-display] [<init_config>]
  swm [options] app list [with-last-used-time] [with-type] [update]
  swm [options] app search [with-type] [index]
  swm [options] app most-used [<count>]
  swm [options] app config show-default
  swm [options] app config list
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

Environment variables:
  SWM_CACHE_DIR
                SWM managed cache directory on PC, which stores the main config file
  SWM_CLI_SUGGESION_LIMIT
                Maximum possible command suggestions when failed to parse user input
  ADB           Path to ADB binary (overrides SWM managed ADB)
  SCRCPY        Path to SCRCPY binary (overrides SWM managed SCRCPY)
  FZF           Path to FZF binary (overrides SWM  managed FZF)
"""

# TODO: save session to all devices with the same name, and restore with the same name

# TODO: hold the main display lock if it is unlocked, till swm is not connected

# TODO: setup network connection between PC client and on device daemon via:
# adb forward tcp:<PC_PORT> tcp:<DEVICE_PORT>
# adb reverse tcp:<DEVICE_PORT> tcp:<PC_PORT>
# deepseek says "adb forward" is suitable for this scenario

# TODO: figure out the protocol used in scrcpy-server, change resolution on the fly using the protocol, track down the port forwarded per scrcpy session
# Note: seems scrcpy is not using adb for port forwarding
# maybe it is communicated via unix socket, via adb shell?
# android.net.LocalServerSocket
# adb shell cat /proc/net/unix
# adb forward tcp:<PC_PORT> localabstract:<ABSTRACT_SOCKET>
# adb reverse localabstract:<ABSTRACT_SOCKET> tcp:<PC_PORT>
# scrcpy/app/src/server.c:sc_adb_tunnel_open
# scrcpy/app/src/adb/adb_tunnel.c:sc_adb_tunnel_open
# SC_SOCKET_NONE

# adb forward --list
# adb reverse --list
# adb forward --remove
# adb forward --remove-all

# TODO: Mark session with PC signature so we can prompt the user if mismatch, like "This is a remote session from xyz, do you trust this machine?"
# TODO: Sign session and other files on android device with public key to ensure integrity (using gnupg or something)

# TODO: provide a loadable, editable app alias file in yaml for faster launch

# BUG: cannot paste when screen is locked
# TODO: unlock the screen automatically using user provided scripts, note down the success rate, last success time, and last failure time

# TODO: suggest possible command completions when the user types a wrong command, using levenshtein

# TODO: when the main screen is locked, clipboard may fail to traverse. warn the user and ask to unlock the screen. (or automatically unlock the screen, if possible)

# TODO: consider a command to mirror the main display

# only import package when needed
# TODO: create a filelock or pid file to prevent multiple instances of the same app running
# TODO: ask the user to "run anyway" when multiple instances of the same app are running

# TODO: dynamically change the fps of scrcpy, only let the foreground one be full and others be 1 fps
# TODO: use platform specific window session manager
# TODO: run swm daemon at first invocation, monitoring window changes, fetch app list in the background, etc

# TODO: globally install this package into the first folder with permission in PATH, or use other tools (actually, adding current binary folder to PATH is better than this, so warn user if not added to PATH)

# TODO: show partial help instead of full help based on the command args given

import os
import platform
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

import omegaconf
from tinydb import Query, Storage, TinyDB
from tinydb.table import Document

__version__ = "0.1.0"


def start_daemon_thread(target, args=(), kwargs={}):
    import threading

    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread

def wait_for_all_threads(threads:list):
    for t in threads:
        t.join()


def format_keyvalue(data: dict):
    ret = []
    for k, v in data.items():
        it = "%s=%s" % (k, v)
        ret.append(it)
    ret = ", ".join(ret)
    return ret


def get_first_laddr_port_with_pid(pid: int):
    # used for finding scrcpy local control port
    import psutil

    conns = psutil.net_connections()
    conns = [it for it in conns if it.pid == pid]
    if len(conns) > 0:
        laddr = conns[0].laddr
        ret = getattr(laddr, "port", None)
        return ret


def parse_dumpsys_active_apps(text: str):
    ret = {"foreground": [], "focused": []}
    lines = grep_lines(text, ["ResumedActivity"])
    # print("Lines:", lines)
    for it in lines:
        if it.startswith("ResumedActivity:"):
            ret["focused"].append(extract_app_id_from_activity_record(it))
        elif it.startswith("topResumedActivity="):
            ret["foreground"].append(extract_app_id_from_activity_record(it))
    # print("Ret:", ret)
    return ret


def extract_app_id_from_activity_record(text: str, return_original_on_failure=True):
    items = text.replace("/", "/ /").split()
    for it in items:
        it = it.strip()
        if it.endswith("/"):
            return it[:-1]
    if return_original_on_failure:
        return text


def parse_display_focus(lines: list[str]):
    ret = {}
    display_id = None
    for it in lines:
        if it.startswith("Display:"):
            display_id = it.split()[1]
            if "mDisplayId" in display_id:  # hope this format won't change?
                display_id = display_id.split("=")[1]
                display_id = int(display_id)
            else:
                display_id = None
        elif it.startswith("mFocusedApp="):
            if "ActivityRecord" in it:
                if display_id is not None:
                    focused_app = extract_app_id_from_activity_record(it)
                    ret[display_id] = focused_app
    return ret


def split_lines(text: str) -> list[str]:
    ret = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            ret.append(line)
    return ret


def grep_lines(
    text: str, whitelist: list[str] = [], blacklist: list[str] = []
) -> list[str]:
    ret = []
    for line in split_lines(text):
        if whitelist and not any(wh in line for wh in whitelist):
            continue
        if blacklist and any(bl in line for bl in blacklist):
            continue
        ret.append(line)
    return ret


def parse_dumpsys_keyvalue_output(output: str):
    lines = output.splitlines()
    ret = {}
    for line in lines:
        line = line.strip()
        if line:
            key, value = line.split("=", 1)
            ret[key.strip()] = value.strip()
    return ret


def suggest_closest_commands(
    possible_commands: list[dict], user_input: str, limit: int
):
    from fuzzywuzzy import fuzz

    assert limit >= 1, "Limit must be greater than zero, given %s" % limit
    ret = possible_commands.copy()
    ret.sort(
        key=lambda x: -fuzz.token_sort_ratio(
            user_input,
            x["matcher"],
        )
    )
    # print("Sorted:", ret)
    ret = [it["display"] for it in ret[:limit]]
    return ret


def remove_option_variable(option: str):
    words = option.split(" ")
    ret = []
    for it in words:
        it = it.strip()
        if it:
            if it[0] not in "([<":
                ret.append(it)
    ret = " ".join(ret)
    return ret


def extract_possible_commands_from_doc():
    assert DOCSTRING, "No docstring found"
    lines = DOCSTRING.split("\n")
    lines = [it.strip() for it in lines]
    ret = [
        dict(matcher=remove_option_variable(it), display=it)
        for it in lines
        if it.startswith("swm ")
    ]
    return ret


def show_suggestion_on_wrong_command(user_input: str, limit: int = 1):
    # print("User input:", user_input)
    possible_commands = extract_possible_commands_from_doc()
    # print("Possible commands:", possible_commands)
    closest_commands = suggest_closest_commands(
        possible_commands=possible_commands, user_input=user_input, limit=limit
    )
    print("Did you mean:", *closest_commands, sep="\n  ")


def get_init_complete_path(basedir: str):
    init_flag = os.path.join(basedir, ".INITIAL_BINARIES_DOWNLOADED")
    return init_flag


def check_init_complete(basedir: str):
    init_flag = get_init_complete_path(basedir)
    return os.path.exists(init_flag)


def test_best_github_mirror(mirror_list: list[str], timeout: float):
    results = []
    for it in mirror_list:
        success, duration = test_internet_connectivity(it, timeout)
        results.append((success, duration, it))
    results = list(filter(lambda x: x[0], results))
    results.sort(key=lambda x: x[1])

    if len(results) > 0:
        return results[0][2]
    else:
        return None


def test_internet_connectivity(url: str, timeout: float):
    import requests

    try:
        response = requests.get(url, verify=False, timeout=timeout)
        return response.status_code == 200, response.elapsed.total_seconds()
    except:
        return False, -1


def download_initial_binaries(basedir: str, mirror_list: list[str]):
    import pathlib

    init_flag = get_init_complete_path(basedir)
    if check_init_complete(basedir):
        print("Initialization complete")
        return
    github_mirror = test_best_github_mirror(mirror_list, timeout=5)
    print("Using mirror: %s" % github_mirror)
    baseurl = "%s/James4Ever0/swm/releases/download/bin/" % github_mirror
    pc_os_arch = (
        "%s-%s" % get_system_and_architecture()
    )  # currently, linux only. let's be honest.
    print("Your PC OS and architecture: %s" % pc_os_arch)
    download_files = [
        "android-binaries.zip",
        "apk.zip",
        "pc-binaries-%s.zip" % pc_os_arch,
    ]
    # now download and unzip all zip files to target directory
    for it in download_files:
        url = baseurl + it
        print("Downloading %s" % url)
        download_and_unzip(url, basedir)
    if os.name == "posix":
        print("Making PC binaries executable")
        subprocess.run(["chmod", "-R", "+x", os.path.join(basedir, "pc-binaries")])
    print("All binaries downloaded")
    pathlib.Path(init_flag).touch()


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


def edit_content(content: str):
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
        tmpfile.write(content)
        tmpfile.flush()
        tmpfile_path = tmpfile.name
        edited_content = edit_or_open_file(tmpfile_path, return_value="content")
        assert type(edited_content) == str
        return edited_content


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
    with requests.get(url, stream=True, allow_redirects=True, verify=False) as response:
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
    if arch == "x64":
        arch = "x86_64"
    elif arch == "arm64":
        arch = "aarch64"
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
    cache_dir: str, bin_name: str, bin_type: str
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

    # 2. Check in cache directory
    cache_path = os.path.join(cache_dir, "pc-binaries", platform_specific_name)
    if os.path.exists(cache_path):
        return cache_path

    # 3. Check in PATH
    path_path = shutil.which(platform_specific_name)
    if path_path:
        return path_path

    # 4. Not found anywhere - attempt to download
    return download_binary_into_cache_dir_and_return_path(
        cache_dir, bin_name=bin_name, bin_type=bin_type
    )


def download_binary_into_cache_dir_and_return_path(
    cache_dir: str, bin_type: str, bin_name: str
) -> str:

    raise NotImplementedError(
        "Downloading is not implemented yet for %s-%s-%s"
        % (*get_system_and_architecture(), bin_name)
    )

    bin_dir = os.path.join(cache_dir, bin_type)
    os.makedirs(bin_dir, exist_ok=True)

    # For demonstration purposes, we'll just create an empty file
    bin_path = os.path.join(bin_dir, bin_name)
    if platform.system() == "Windows":
        bin_path += ".exe"

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
        assert type(adb_wrapper.device) == str
        self.device_id = adb_wrapper.device
        self._db = TinyDB(db_path, storage=self.storage)

    def write_previous_ime(self, previous_ime: str):
        PreviousIme = Query()
        device_id = self.device_id
        self._db.table("previous_ime").upsert(
            dict(device_id=device_id, previous_ime=previous_ime),
            (PreviousIme.device_id == device_id),
        )

    def read_previous_ime(self):
        PreviousIme = Query()
        device_id = self.device_id

        # Search for matching document
        result = self._db.table("previous_ime").get(
            (PreviousIme.device_id == device_id)
        )
        # Return datetime object if found, None otherwise

        if result:
            assert type(result) == Document
            ret = result["previous_ime"]
            assert type(ret) == str
            return ret

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

    def update_app_last_used_time(self, device_id: str, app_id: str):
        last_used_time = datetime.now()
        self.write_app_last_used_time(device_id, app_id, last_used_time)

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
        self.adb = self._get_binary("adb", "pc-binaries")
        self.scrcpy = self._get_binary("scrcpy", "pc-binaries")
        self.fzf = self._get_binary("fzf", "pc-binaries")

        # Initialize components
        self.adb_wrapper = AdbWrapper(self.adb, self.config)
        self.scrcpy_wrapper = ScrcpyWrapper(self.scrcpy, self)
        self.fzf_wrapper = FzfWrapper(self.fzf)

        # Device management
        self.current_device = None

        # Initialize managers
        self.app_manager = AppManager(self)
        self.session_manager = SessionManager(self)
        self.device_manager = DeviceManager(self)

        self.on_device_db = None

    @property
    def fingerprint(self):
        import uuid

        if os.path.exists(self._fingerprint_path):
            with open(self._fingerprint_path, "r") as f:
                return f.read()
        else:
            ret = str(uuid.uuid4())
            with open(self._fingerprint_path, "w+") as f:
                f.write(ret)
            return ret

    @property
    def _fingerprint_path(self):
        return os.path.join(self.cache_dir, ".fingerprint")

    @property
    def _trusted_fingerprints_path(self):
        return os.path.join(self.cache_dir, ".trusted_fingerprints")

    def trust_fingerprint(self, fingerprint: str):
        with open(self._trusted_fingerprints_path, "a+") as f:
            f.write(fingerprint + "\n")

    def check_fingerprint_trusted(self, fingerprint: str):
        trusted_fingerprints = self.list_trusted_fingerprints()
        ret = fingerprint in trusted_fingerprints
        return ret

    def list_trusted_fingerprints(self):
        ret = []
        if os.path.exists(self._trusted_fingerprints_path):
            with open(self._trusted_fingerprints_path, "r") as f:
                contents = f.read()
                ret = split_lines(contents)
        return ret

    def load_swm_on_device_db(self):
        db_path = os.path.join(self.config.android_session_storage_path, "db.json")
        self.on_device_db = SWMOnDeviceDatabase(db_path, self.adb_wrapper)

    def _get_binary(self, name: str, bin_type: str) -> str:
        return search_or_obtain_binary_path_from_environmental_variable_or_download(
            self.cache_dir, name, bin_type
        )

    def set_current_device(self, device_id: str):
        self.current_device = device_id
        self.adb_wrapper.set_device(device_id)
        self.scrcpy_wrapper.set_device(device_id)

        # now check for android version
        self.check_android_version()

    def check_android_version(self):
        # multi display: 8
        # ref: https://stackoverflow.com/questions/63333696/which-is-the-first-version-of-android-that-support-multi-display
        # multi display with different resolution: 9
        # ref: https://source.android.com/docs/core/display/multi_display/displays
        minimum_android_version_for_multi_displays = 10  # from source code of scrcpy
        android_version = self.adb_wrapper.get_android_version()
        print("Android version:", android_version)
        if android_version < minimum_android_version_for_multi_displays:
            raise RuntimeError(
                "Android version must be %s or higher"
                % minimum_android_version_for_multi_displays
            )

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
    if "last_used_time" in df.columns:
        df["last_used_time"] = df["last_used_time"].transform(
            lambda x: x.strftime("%Y-%m-%d %H:%M")
        )
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
        cmd = [
            "bash",
            "-c",
            "cmd package resolve-activity --brief %s | tail -n 1" % app_id,
        ]
        output = self.swm.adb_wrapper.check_output_shell(cmd).strip()
        return output

    def start_app_in_given_display(self, app_id: str, display_id: int):
        # adb shell am start --display <DISPLAY_ID> -n <PACKAGE/ACTIVITY>
        app_main_activity = self.resolve_app_main_activity(app_id)
        self.swm.adb_wrapper.execute_shell(
            ["am", "start", "--display", str(display_id), "-n", app_main_activity]
        )

    def resolve_app_query(self, query: str):
        ret = query
        if not self.check_app_existance(query):
            # this is definitely a query
            ret = self.search(index=False, query=query)
        return ret

    # let's mark it rooted device only.
    # we get the package path, data path and get last modification date of these files
    # or use java to access UsageStats
    def get_app_last_used_time_from_device(self, app_id: str):
        data_path = "/data/data/%s" % app_id
        if self.swm.adb_wrapper.test_path_existance_su(data_path):
            cmd = "ls -Artls '%s' | tail -n 1 | awk '{print $7,$8}'" % data_path
            last_used_time = self.swm.adb_wrapper.check_output_su(cmd).strip()
            # format: 2022-12-31 12:00
            last_used_time = datetime.strptime(last_used_time, "%Y-%m-%d %H:%M")
            return last_used_time

    def get_app_last_used_time_from_db(self, package_id: str):
        assert self.swm.on_device_db
        device_id = self.swm.current_device
        last_used_time = self.swm.on_device_db.get_app_last_used_time(
            device_id, package_id
        )
        return last_used_time

    def write_app_last_used_time_to_db(self, package_id: str, last_used_time: datetime):
        assert self.swm.on_device_db
        device_id = self.swm.current_device
        self.swm.on_device_db.write_app_last_used_time(
            device_id, package_id, last_used_time
        )

    def search(self, index: bool, query: Optional[str] = None):
        apps = self.list()
        items = []
        for i, it in enumerate(apps):
            line = f"{it['alias']}\t{it['id']}"
            if index:
                line = f"[{i+1}]\t{line}"
            items.append(line)
        selected = self.swm.fzf_wrapper.select_item(items, query=query)
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
        self.swm.adb_wrapper.enable_and_set_adb_keyboard()

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

    def check_clipboard_malfunction(self):
        display_and_lock_state = self.swm.adb_wrapper.get_display_and_lock_state()
        print("Display and lock state: %s" % display_and_lock_state)
        clipboard_may_malfunction = False
        if "_locked" in display_and_lock_state:
            clipboard_may_malfunction = True
            print("Device is locked")
        if "off_" in display_and_lock_state:
            clipboard_may_malfunction = True
            print("Main display is off")
        if display_and_lock_state == "unknown":
            clipboard_may_malfunction = True
            print("Warning: Device display and lock state unknown")
        if clipboard_may_malfunction:
            print("Warning: Clipboard may malfunction")
        return clipboard_may_malfunction

    def get_app_config(self, config_name: str):
        assert self.check_app_config_existance(config_name)
        app_config = self.get_or_create_app_config(config_name)
        return app_config

    def run(
        self, app_id: str, init_config: Optional[str] = None, new_display: bool = True
    ):
        # TODO: recreate the scrcpy instance if it is exited abnormally, such as app closed on device
        self.check_clipboard_malfunction()
        if not self.check_app_existance(app_id):
            raise NoAppError(
                "Applicaion %s does not exist on device %s"
                % (app_id, self.swm.current_device)
            )
        # TODO: memorize the last scrcpy run args, by default in swm config
        # Get app config
        env = {}
        if init_config:
            app_config = self.get_app_config(init_config)
        else:
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

        # Write last used time to db
        self.update_app_last_used_time_to_db(app_id)
        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(
            app_id,
            init_config=init_config,
            window_params=win,
            scrcpy_args=scrcpy_args,
            title=title,
            new_display=new_display,
            use_adb_keyboard=use_adb_keyboard,
            env=env,
        )

    def update_app_last_used_time_to_db(self, app_id: str):
        # we cannot update the last used time at device, since it is managed by android
        assert self.swm.current_device, "No current device being set"
        assert self.swm.on_device_db, (
            "Device '%s' missing on device db" % self.swm.current_device
        )
        device_id = self.swm.current_device
        self.swm.on_device_db.update_app_last_used_time(device_id, app_id)

    def edit_app_config(self, app_name: str) -> bool:
        # return True if edited, else False
        print(f"Editing config for {app_name}")
        app_config_path = self.get_app_config_path(app_name)
        self.get_or_create_app_config(app_name)
        content = self.swm.adb_wrapper.read_file(app_config_path)
        edited_content = edit_content(content)
        ret = edited_content != content
        if ret:
            self.swm.adb_wrapper.write_file(app_config_path, edited_content)
        assert type(ret) == bool
        return ret

    def copy_app_config(self, source_name: str, target_name: str):
        if target_name == "default":
            raise ValueError("Target name cannot be 'default'")
        if self.check_app_config_existance(target_name):
            raise ValueError("Target '%s' still exists. Consider using reference?")

        if source_name == "default":
            config_yaml_content = self.default_app_config
        elif source_name in self.list_app_config(print_result=False):
            source_config_path = self.get_app_config_path(source_name)

            config_yaml_content = self.swm.adb_wrapper.read_file(source_config_path)
        else:
            raise ValueError("Source '%s' does not exist" % source_name)

        target_config_path = self.get_app_config_path(target_name)
        self.swm.adb_wrapper.write_file(target_config_path, config_yaml_content)

    def list_app_config(self, print_result: bool):
        # display config name, categorize them into two groups: default and custom
        # you may configure the default config of an app to use a custom config
        # both default and custom one could be referred in default config, but custom config cannot refer others
        # if one default config is being renamed as custom config, then all reference shall be flattened
        app_config_yamls = self.swm.adb_wrapper.listdir(self.app_config_dir)
        app_config_names = [
            os.path.splitext(it)[0] for it in app_config_yamls if it.endswith(".yaml")
        ]
        if print_result:
            self.display_app_config(app_config_names)
        return app_config_names

    def display_app_config(self, app_config_names: List[str]):
        import pandas

        records = []
        for it in app_config_names:
            app_exists = self.check_app_existance(it)
            if app_exists:
                _type = "app"
            else:
                _type = "custom"
            rec = dict(name=it, type=_type)
            records.append(rec)
        df = pandas.DataFrame(records)
        # now display this dataframe
        print(df.to_string(index=False))

    def show_app_config(self, app_name: str):
        config = self.get_or_create_app_config(app_name)
        print(pretty_print_json(config))

    @property
    def app_config_dir(self):
        device_id = self.swm.current_device
        assert device_id
        ret = os.path.join(
            self.swm.config.android_session_storage_path, "app_config"
        )  # TODO: had better to separate devices, though. could add suffix to config name, in order to share config
        return ret

    def get_app_config_path(self, app_name: str):
        app_config_dir = self.app_config_dir
        self.swm.adb_wrapper.ensure_dir_existance(app_config_dir)

        app_config_path = os.path.join(app_config_dir, f"{app_name}.yaml")
        return app_config_path

    def check_app_config_existance(self, config_name: str):
        config_path = self.get_app_config_path(config_name)
        ret = self.swm.adb_wrapper.test_path_existance(config_path)
        return ret

    def resolve_app_config_reference(
        self, ref: str, sources: List[str] = []
    ):  # BUG: if you mark List as "list" it will be resolved into class method "list"
        if ref == "default":
            raise ValueError("Reference cannot be 'default'")
        if ref in sources:
            raise ValueError("Loop reference found for %s in %s" % (ref, sources))
        # this ref must exists
        assert ref in self.list_app_config(print_result=False), (
            "Reference %s does not exist" % ref
        )
        ret = self.get_or_create_app_config(ref, resolve_reference=False)
        ref_in_ref = ret.get("reference", None)
        if ref_in_ref:
            ret = self.resolve_app_config_reference(
                ref=ref_in_ref, sources=sources + [ref]
            )
        return ret

    def get_or_create_app_config(self, app_name: str, resolve_reference=True) -> Dict:
        import yaml

        default_config_obj = yaml.safe_load(self.default_app_config)

        if app_name == "default":  # not creating it
            return default_config_obj

        app_config_path = self.get_app_config_path(app_name)

        if not self.swm.adb_wrapper.test_path_existance(app_config_path):
            print("Creating default config for app:", app_name)
            # Write default YAML template with comments
            self.swm.adb_wrapper.write_file(app_config_path, self.default_app_config)
            return default_config_obj

        yaml_content = self.swm.adb_wrapper.read_file(app_config_path)
        ret = yaml.safe_load(yaml_content)
        if resolve_reference:
            ref = ret.get("reference", None)
            if ref:
                ret = self.resolve_app_config_reference(ref, sources=[app_name])
        return ret

    @property
    def default_app_config(self):
        return """# Application configuration template
# All settings are optional - uncomment and modify as needed

# uncomment the below line for using custom config
# reference: <custom_config_name>

# notice, if you reference any config here, the below settings will be ignored

# arguments passed to scrcpy
scrcpy_args: []

# install and enable adb keyboard, useful for using PC input method when multi-tasking
use_adb_keyboard: true

# retrieve and display app icon instead of the default scrcpy icon
retrieve_app_icon: true
"""

    def save_app_config(self, app_name: str, config: Dict):
        import yaml

        app_config_path = self.get_app_config_path(app_name)
        with open(app_config_path, "w") as f:
            yaml.safe_dump(config, f)

    def list_all_apps(self, update_cache=False) -> List[dict[str, str]]:
        # package_ids = self.swm.adb_wrapper.list_packages()
        (
            package_list,
            cache_expired,
        ) = self.swm.scrcpy_wrapper.load_package_id_and_alias_cache()
        if update_cache or cache_expired:
            package_list = self.swm.scrcpy_wrapper.list_package_id_and_alias()
            self.swm.scrcpy_wrapper.save_package_id_and_alias_cache(package_list)
        assert type(package_list) == list

        for it in package_list:
            package_id = it["id"]
            if update_cache:
                last_used_time = self.get_app_last_used_time_from_device(package_id)
                if last_used_time is None:
                    last_used_time = self.get_app_last_used_time_from_db(package_id)
                else:
                    # update db
                    self.write_app_last_used_time_to_db(package_id, last_used_time)
            else:
                last_used_time = self.get_app_last_used_time_from_db(package_id)
                if last_used_time is None:
                    last_used_time = self.get_app_last_used_time_from_device(package_id)
                    if last_used_time is not None:
                        # update db
                        self.write_app_last_used_time_to_db(package_id, last_used_time)
            if last_used_time is None:
                last_used_time = datetime.fromtimestamp(0)
            it["last_used_time"] = last_used_time
        return package_list

    def list_most_used_apps(
        self, limit: int, update_cache=False
    ) -> List[dict[str, Any]]:
        # Placeholder implementation
        all_apps = self.list_all_apps(update_cache=update_cache)
        all_apps.sort(key=lambda x: -x["last_used_time"].timestamp())  # type: ignore
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
        print(
            "Warning: 'template_session_config' has not been implemented, returning placeholder instead."
        )
        return """
# Session template config
# Uncomment any options below and begin customization
"""

    def resolve_session_query(self, query: str):
        if query in self.list():
            return query
        else:
            return self.search(query)

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

    def search(self, query: Optional[str] = None):
        sessions = self.list()
        return self.swm.fzf_wrapper.select_item(sessions, query=query)

    def list(self) -> List[str]:
        session_json_paths = [
            f for f in self.adb_wrapper.listdir(self.session_dir) if f.endswith(".json")
        ]
        session_names = [os.path.splitext(it)[0] for it in session_json_paths]
        # session_names.append("default")
        # TODO: no one can save a session named "default", or one may customize this behavior through swm pc/android config, somehow allow this to happen
        return session_names

    def get_pc_info(self):
        import socket
        import getpass

        # Get the current username
        username = getpass.getuser()
        hostname = socket.gethostname()
        fingerprint = self.swm.fingerprint
        ret = dict(hostname=hostname, user=username, fingerprint=fingerprint)
        return ret

    def save(self, session_name: str):
        # TODO: store all running app launch parameters at "swm_scrcpy_proc_pid_path", then we read and merge them here
        # TODO: must verify the process is alive by its pid, or exclude it
        import time

        assert session_name != "default", "Cannot save a session named 'default'"

        device = self.swm.current_device
        assert device
        print("Saving session for device:", device)
        # Get current window positions and app states
        pc = self.get_pc_info()
        session_data = {
            "timestamp": time.time(),
            "device": device,
            "pc": pc,
            # "windows": self._get_window_states(),
            "windows": self.get_window_states_for_device_by_scrcpy_pid_files(),
        }

        self._save_session_data(session_name, session_data)

    def get_window_states_for_device_by_scrcpy_pid_files(self):
        swm_info_list = (
            self.swm.scrcpy_wrapper.get_running_swm_managed_scrcpy_info_list()
        )
        return swm_info_list

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

    def get_session_path(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.yaml")
        return session_path

    def _save_session_data(self, session_name: str, session_data: dict):
        import yaml

        session_path = self.get_session_path(session_name)
        content = yaml.safe_dump(session_data)
        self.swm.adb_wrapper.write_file(session_path, content)

    def check_pc_info(self, session_pc_info: dict):
        current_pc_info = self.get_pc_info()
        session_fingerprint = session_pc_info["fingerprint"]
        current_fingerprint = current_pc_info["fingerprint"]
        if current_fingerprint == session_fingerprint:
            return True
        else:
            fingerprint_trusted = self.swm.check_fingerprint_trusted(
                session_fingerprint
            )

            if fingerprint_trusted:
                return True
            else:
                # warn the user
                print("Current PC:", format_keyvalue(current_pc_info))
                print("Session PC:", format_keyvalue(session_pc_info))
                print("Warning: PC not trusted")
                ans = prompt_for_option_selection(
                    ["y", "n"],
                    "Do you trust this PC (fingerprint: %s) ?" % session_fingerprint,
                )
                if ans == "y":
                    self.swm.trust_fingerprint(session_fingerprint)
                    return True
                # ask the user to trust the pc and enlist its fingerprint
        print("User declined the trust request")
        return False

    def restore(self, session_name: str):
        import yaml

        session_path = self.get_session_path(session_name)

        if not self.swm.adb_wrapper.test_path_existance(session_path):
            raise FileNotFoundError(f"Session not found: {session_name}")

        content = self.swm.adb_wrapper.read_file(session_path)
        session_data = yaml.safe_load(content)

        session_pc_info = session_data["pc"]

        if not self.check_pc_info(session_pc_info):
            print("Not loading session '%s'" % session_name)
            return
        
        threads = []

        # Restore each window
        for scrcpy_info in session_data["windows"]:
            launch_params = scrcpy_info["launch_params"]
            app_name = launch_params["package_name"]
            is_app_running = self.swm.scrcpy_wrapper.check_app_running(app_name)
            if not is_app_running:
                # TODO: run this in detached mode, or print log with different pid
                # TODO: save and restore window positioning
                t = start_daemon_thread(
                    self.swm.scrcpy_wrapper.launch_app, kwargs=launch_params
                )
                threads.append(t)
        wait_for_all_threads(threads)

    def delete(self, session_name: str) -> bool:
        session_path = self.get_session_path(session_name)
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

    def search(self, query: Optional[str] = None):
        return self.swm.fzf_wrapper.select_item(
            self.list(print_formatted=False), query=query
        )

    def resolve_device_query(self, query: str):
        if query in self.list(print_formatted=False):
            device_id = query
        else:
            device_id = self.search(query)
        return device_id

    def select(self, query: str):
        device_id = self.resolve_device_query(query)
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

    def listdir(self, path: str):
        assert self.test_path_existance(path)
        output = self.check_output_shell(["ls", "-1", path])
        ret = split_lines(output)
        return ret

    def check_has_root(self):
        return self.execute_su_cmd("whoami", check=False).returncode == 0

    def get_current_ime(self):
        # does not require su, but anyway we just use su
        output = self.check_output_su(
            "settings get secure default_input_method", check=False
        )
        return output

    def list_active_imes(self):
        return self.check_output_su("ime list -s").splitlines()

    def set_current_ime(self, ime_name):
        self.execute_su_cmd(f"settings put secure default_input_method {ime_name}")

    def check_output_su(self, cmd: str, **kwargs):
        return self.check_output_shell(["su", "-c", cmd], **kwargs)

    def check_output_shell(self, cmd_args: list[str], **kwargs):
        return self.check_output(["shell"] + cmd_args, **kwargs)

    # TODO: if app is not foreground, or is ime input target but has different display id, then we close the corresponding scrcpy window

    def get_display_density(self, display_id: int):
        # adb shell wm density -d <display_id>
        # first, it must exist
        output = self.check_output(
            ["shell", "wm", "density", "-d", str(display_id)]
        ).strip()
        ret = output.split(":")[-1].strip()
        ret = int(ret)
        if ret <= 0:
            print("Warning: display %s does not exist" % display_id)
        else:
            return ret

    def check_app_in_display(self, app_id: str, display_id: int):
        display_focus = self.get_display_current_focus().get(display_id, "")
        ret = (app_id + "/") in (display_focus + "/")
        return ret

    def get_display_current_focus(self):
        # adb shell dumpsys window | grep "ime" | grep display
        # adb shell dumpsys window displays | grep "mCurrentFocus"
        # adb shell dumpsys window displays | grep -E "mDisplayId|mFocusedApp"

        # we can get display id and current focused app per display here
        # just need to parse section "WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)"

        output = self.check_output(["shell", "dumpsys", "window", "displays"])
        lines = grep_lines(output, ["mDisplayId", "mFocusedApp"])
        ret = parse_display_focus(lines)
        # print("Ret:", ret)
        return ret

    def check_app_is_foreground(self, app_id: str):
        # convert the binary output from "wm dump-visible-window-views" into ascii byte by byte, those not viewable into "."
        # adb shell wm dump-visible-window-views | xxd | grep <app_id>

        # or use the readable output from dumpsys
        # adb shell "dumpsys activity activities | grep ResumedActivity" | grep <app_id>
        # topResumedActivity: on top of specific display
        # ResumedActivity: the current focused app
        output = self.check_output(["shell", "dumpsys", "activity", "activities"])
        data = parse_dumpsys_active_apps(output)
        foreground_apps = data["foreground"]
        # print("Foreground apps:", foreground_apps)
        for it in foreground_apps:
            if (app_id + "/") in (it + "/"):
                return True
        return False

    def check_app_existance(self, app_id):
        apk_path = self.get_app_apk_path(app_id)
        if apk_path:
            return True
        return False

    def get_display_and_lock_state(self):
        # reference: https://stackoverflow.com/questions/35275828/is-there-a-way-to-check-if-android-device-screen-is-locked-via-adb
        # adb shell dumpsys power | grep 'mHolding'
        # If both are false, the display is off.
        # If mHoldingWakeLockSuspendBlocker is false, and mHoldingDisplaySuspendBlocker is true, the display is on, but locked.
        # If both are true, the display is on.
        output = self.check_output(["shell", "dumpsys", "power"])
        lines = grep_lines(output, ["mHolding"])
        data = parse_dumpsys_keyvalue_output("\n".join(lines))
        if (
            data.get("mHoldingWakeLockSuspendBlocker") == "false"
            and data.get("mHoldingDisplaySuspendBlocker") == "false"
        ):
            ret = "off_locked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "true"
            and data.get("mHoldingDisplaySuspendBlocker") == "true"
        ):
            ret = "on_unlocked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "true"
            and data.get("mHoldingDisplaySuspendBlocker") == "false"
        ):
            ret = "on_locked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "false"
            and data.get("mHoldingDisplaySuspendBlocker") == "true"
        ):
            ret = "off_unlocked"
        else:
            ret = "unknown"
        return ret

    def adb_keyboard_input_text(self, text: str):
        # adb shell am broadcast -a ADB_INPUT_B64 --es msg `echo -n '你好' | base64`
        base64_text = encode_base64_str(text)
        self.execute_shell(
            ["am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", base64_text]
        )
        # TODO: restore the previously using keyboard after swm being detached, either manually or using script/apk

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

    def test_path_existance_su(self, remote_path: str):
        cmd = "test -e '%s'" % remote_path
        result = self.execute_su_cmd(cmd, check=False)
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

    def check_output(self, args: List[str], device_id=None, **kwargs) -> str:
        return self.execute(
            args, capture=True, device_id=device_id, **kwargs
        ).stdout.strip()

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
        adb_keyboard_app_id = "com.android.adbkeyboard"
        installed_app_id_list = self.list_packages()
        if adb_keyboard_app_id not in installed_app_id_list:
            apk_path = self.get_swm_apk_path("ADBKeyboard")
            self.install_apk(apk_path)

    def execute_su_cmd(self, cmd: str, **kwargs):
        return self.execute(["shell", "su", "-c", cmd], **kwargs)

    def execute_su_script(self, script: str, **kwargs):
        tmpfile = "/sdcard/.swm/tmp.sh"
        self.write_file(tmpfile, script)
        cmd = "sh %s" % tmpfile
        return self.execute_su_cmd(cmd, **kwargs)

    def enable_and_set_specific_keyboard(self, keyboard_activity_name: str):
        self.execute_su_cmd("ime enable %s" % keyboard_activity_name)
        self.execute_su_cmd("ime set %s" % keyboard_activity_name)

    def enable_and_set_adb_keyboard(self):
        keyboard_activity_name = "com.android.adbkeyboard/.AdbIME"
        if self.get_current_ime() != keyboard_activity_name:
            self.enable_and_set_specific_keyboard(keyboard_activity_name)

    def disable_adb_keyboard(self):
        self.execute(["shell", "am", "force-stop", "com.android.adbkeyboard"])

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
        output = self.check_output(["shell", "pm", "path", app_id], check=False).strip()
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

    def get_android_version(self) -> int:
        ret = self.check_output(["shell", "getprop", "ro.build.version.release"])
        ret = int(ret)
        return ret

    def get_device_architecture(self) -> str:
        return self.check_output(["shell", "getprop", "ro.product.cpu.abi"])

    def list_device_ids(
        self,
        status_blacklist: list[str] = ["unauthorized", "fastboot"],
        with_status: bool = False,
    ) -> List:
        # TODO: detect and filter unauthorized and abnormal devices
        output = self.check_output(["devices"])
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                elements = line.split()
                device_id = elements[0]
                device_status = elements[1]
                if device_status not in status_blacklist:
                    if with_status:
                        devices.append({"id": device_id, "status": device_status})
                    else:
                        devices.append(device_id)
                else:
                    print(
                        "Warning: device %s status '%s' is in blacklist %s thus skipped"
                        % (device_id, device_status, status_blacklist)
                    )
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

    def ensure_dir_existance(self, dir_path: str):
        if self.test_path_existance(dir_path):
            return
        print("Directory %s not found, creating it now..." % dir_path)
        self.create_dirs(dir_path)

    def create_swm_dir(self):
        swm_dir = self.remote_swm_dir
        self.ensure_dir_existance(swm_dir)

    def create_dirs(self, dirpath: str):
        self.execute(["shell", "mkdir", "-p", dirpath])

    def push_aapt(self, device_path: Optional[str] = None):
        if device_path is None:
            device_path = os.path.join(self.config.android_session_storage_path, "aapt")
        device_architecture = self.get_device_architecture()
        local_aapt_path = os.path.join(
            self.config.cache_dir, "android-binaries", "aapt-%s" % device_architecture
        )
        self.execute(["push", local_aapt_path, device_path])
        self.execute(["shell", "chmod", "755", device_path])

    def pull_session(self, session_name: str, local_path: str):
        remote_path = os.path.join(
            self.config.android_session_storage_path, session_name
        )
        self.execute(["pull", remote_path, local_path])


class ScrcpyWrapper:
    def __init__(self, scrcpy_path: str, swm: "SWM"):
        self.scrcpy_path = scrcpy_path
        self.config = swm.config
        self.device = swm.config.get("device")
        self.adb_wrapper = swm.adb_wrapper
        self.swm = swm

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
        # will not list apps without activity or UI
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

    def start_sidecar_scrcpy_monitor_control_port(self, proc: subprocess.Popen):
        import time

        proc_pid = proc.pid

        def monitor_control_port():
            while True:
                time.sleep(1)
                port = get_first_laddr_port_with_pid(proc_pid)
                if port:
                    print("Control port:", port)
                    setattr(proc, "control_port", port)
                    break

        start_daemon_thread(monitor_control_port)

    def launch_app(
        self,
        package_name: str,
        init_config: Optional[str] = None,
        window_params: Optional[Dict] = None,
        scrcpy_args: Optional[list[str]] = None,
        new_display=True,
        title: Optional[str] = None,
        no_audio=True,
        use_adb_keyboard=False,
        env={},
    ):
        import signal
        import psutil
        import json

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

        if no_audio:
            args.extend(["--no-audio"])

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
        _env = os.environ.copy()
        _env.update(env)
        # merge stderr with stdout
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            env=_env,
        )
        proc_pid = proc.pid

        print("Scrcpy PID:", proc_pid)

        self.start_sidecar_scrcpy_app_monitor_thread(package_name, proc)

        self.start_sidecar_scrcpy_monitor_control_port(proc)

        if new_display:
            self.start_sidecar_scrcpy_stdout_monitor_thread(proc)
        else:
            setattr(proc, "display_id", 0)
        assert proc.stderr
        previous_ime = self.get_previous_ime()
        if not previous_ime:
            print("Warning: previous ime unrecognized")

        # TODO: capture stdout for getting new display id
        # TODO: collect missing char into batches and execute once every 0.5 seconds
        # TODO: restart the app in given display if exited, or just close the window (configure this behavior as an option "on_app_exit")
        # not to use the compat "launch_params" since we may have trouble when the config file is edited.
        # TODO: configure this behavior further, by prefer "init_config" or "freezed_parameters"
        # TODO: build "env" when prefer "freezed_parameters"
        launch_params = dict(
            package_name=package_name,
            init_config=init_config,
            window_params=window_params,
            scrcpy_args=scrcpy_args,
            new_display=new_display,
            title=title,
            no_audio=no_audio,
            use_adb_keyboard=use_adb_keyboard,
        )
        try:
            # write the pid to the path
            swm_scrcpy_proc_pid_path = self.generate_swm_scrcpy_proc_pid_path()
            with open(swm_scrcpy_proc_pid_path, "w") as f:
                data = dict(
                    pid=proc_pid, device_id=self.device, launch_params=launch_params
                )
                content_data = json.dumps(data, indent=4, ensure_ascii=False)
                f.write(content_data)
                # TODO: write additional launch parameters here so we can create a session based on these files
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
            # kill by pid, if alive

            if psutil.pid_exists(proc_pid):
                try:
                    os.kill(proc_pid, signal.SIGKILL)
                    proc.kill()
                except:
                    print("Error while trying to kill the scrcpy process %s" % proc_pid)

            if os.path.exists(swm_scrcpy_proc_pid_path):
                if not psutil.pid_exists(proc_pid):
                    os.remove(swm_scrcpy_proc_pid_path)
                else:
                    print(
                        "Not removing PID file %s since the scrcpy process %s is still running"
                        % (swm_scrcpy_proc_pid_path, proc_pid)
                    )

            no_swm_process_running = not self.has_swm_process_running

            if no_swm_process_running:
                if previous_ime:
                    print("Reverting to previous ime")
                    self.adb_wrapper.enable_and_set_specific_keyboard(previous_ime)

    def check_app_in_display(self, app_id: str, display_id: int):
        app_is_foreground = self.adb_wrapper.check_app_is_foreground(app_id)
        app_is_in_display = self.adb_wrapper.check_app_in_display(app_id, display_id)

        if not app_is_foreground:
            print("App %s is not in foreground" % app_id)
        if not app_is_in_display:
            print("App %s is not in display %s" % (app_id, display_id))
        return app_is_foreground and app_is_in_display

    def start_sidecar_scrcpy_stdout_monitor_thread(self, proc: subprocess.Popen):
        assert proc.stdout
        proc_stdout = proc.stdout

        def monitor_stdout_and_set_attribute():
            for line in proc_stdout:
                line = line.strip()
                print("<scrcpy stdout> %s" % line)
                if line.startswith("[server] INFO: New display:"):
                    display_id = line.split("=")[-1].strip("()")
                    display_id = int(display_id)
                    setattr(proc, "display_id", display_id)

        start_daemon_thread(monitor_stdout_and_set_attribute)

    def scrcpy_app_monitor(self, app_id: str, proc: subprocess.Popen):
        # import signal
        import time
        import psutil

        proc_pid = proc.pid

        while True:
            time.sleep(0.2)
            if hasattr(proc, "display_id"):
                display_id = getattr(proc, "display_id")
                break

        last_app_in_display = app_in_display = self.check_app_in_display(
            app_id, display_id
        )
        while True:
            last_app_in_display = app_in_display
            time.sleep(1)
            app_in_display = self.check_app_in_display(app_id, display_id)
            process_alive = psutil.pid_exists(proc_pid)
            if not process_alive:
                break
            if (
                last_app_in_display == True and app_in_display == False
            ):  # app terminated
                proc.terminate()
                # os.kill(proc_pid, signal.SIGKILL)
                break

    def get_previous_ime(self):
        adbkeyboard_ime = "com.android.adbkeyboard/.AdbIME"
        previous_ime = self.adb_wrapper.get_current_ime()
        if previous_ime == adbkeyboard_ime:
            previous_ime = self.read_previous_ime_from_device()
        else:
            self.store_previous_ime_to_device(previous_ime)
        return previous_ime

    def read_previous_ime_from_device(self):
        assert self.swm.on_device_db
        return self.swm.on_device_db.read_previous_ime()

    def store_previous_ime_to_device(self, previous_ime: str):
        assert self.swm.on_device_db
        self.swm.on_device_db.write_previous_ime(previous_ime)

    def start_sidecar_scrcpy_app_monitor_thread(
        self, app_id: str, proc: subprocess.Popen
    ):
        # configure this thread with daemon=True
        start_daemon_thread(
            target=self.scrcpy_app_monitor, kwargs=dict(app_id=app_id, proc=proc)
        )

    def generate_swm_scrcpy_proc_pid_path(self):
        import uuid

        unique_id = str(uuid.uuid4())
        filename = "%s.json" % unique_id
        ret = os.path.join(self.swm_scrcpy_proc_pid_basedir, filename)
        return ret

    @property
    def swm_scrcpy_proc_pid_basedir(self):
        ret = os.path.join(self.config.cache_dir, "swm_scrcpy_proc_pid")
        if not os.path.exists(ret):
            os.makedirs(ret, exist_ok=True)
        return ret

    @property
    def has_swm_process_running(self):
        return len(self.get_running_swm_managed_scrcpy_pids()) > 0

    def list_swm_managed_scrcpy_pid_files(self):
        ret = []
        for it in os.listdir(self.swm_scrcpy_proc_pid_basedir):
            path = os.path.join(self.swm_scrcpy_proc_pid_basedir, it)
            if os.path.isfile(path):
                if not path.endswith(".json"):
                    continue
                ret.append(path)
        return ret

    def get_running_swm_managed_scrcpy_pids(self):
        ret = self.get_running_swm_managed_scrcpy_info_list()
        ret = [it["pid"] for it in ret]
        return ret

    def check_app_running(self, app_id: str):
        running_app_ids = self.get_running_app_ids()
        ret = app_id in running_app_ids
        return ret

    def get_running_app_ids(self):
        scrcpy_info_list = self.get_running_swm_managed_scrcpy_info_list()
        ret = [it["launch_params"]["package_name"] for it in scrcpy_info_list]
        return ret

    def get_running_swm_managed_scrcpy_info_list(self):
        import psutil
        import json

        ret = []
        assert self.device
        for path in self.list_swm_managed_scrcpy_pid_files():
            with open(path, "r") as f:
                data = json.load(f)
                device_id = data["device_id"]
                if device_id != self.device:
                    continue
                pid = data["pid"]
                pid = int(pid)
                if psutil.pid_exists(pid):
                    ret.append(data)
        return ret

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

    def select_item(self, items: List[str], query: Optional[str] = None) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w+") as tmp:
            tmp.write("\n".join(items))
            tmp.flush()

            cmd = [self.fzf_path, "--layout=reverse"]
            if query:
                cmd.extend(["--query", query])
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


def load_or_create_config(cache_dir: str, config_path: str):
    if os.path.exists(config_path):
        print("Loading existing config from:", config_path)
        config = omegaconf.OmegaConf.load(config_path)
    else:
        print("Creating default config at:", config_path)
        config = create_default_config(cache_dir)
        omegaconf.OmegaConf.save(config, config_path)
    assert type(config) == omegaconf.DictConfig
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


def parse_args(cli_suggestion_limit: int):
    from docopt import docopt, DocoptExit
    import sys

    try:
        return docopt(__doc__, version=f"SWM {__version__}", options_first=True)
    except DocoptExit:
        # print the docstring
        print(DOCSTRING)
        # must be something wrong with the arguments
        argv = sys.argv
        user_input = "swm " + (" ".join(argv[1:]))
        show_suggestion_on_wrong_command(user_input, limit=cli_suggestion_limit)
        # TODO: configure "limit" in swm config yaml
    exit(1)


def main():
    import sys

    # Setup cache directory
    default_cache_dir = os.path.expanduser("~/.swm")

    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", default_cache_dir)
    # TODO: Include environment variable documentation into help and error message
    os.makedirs(SWM_CACHE_DIR, exist_ok=True)
    CLI_SUGGESION_LIMIT = os.environ.get("SWM_CLI_SUGGESION_LIMIT", 1)
    CLI_SUGGESION_LIMIT = int(CLI_SUGGESION_LIMIT)
    # Parse CLI arguments
    args = parse_args(CLI_SUGGESION_LIMIT)

    config_path = args["--config"]
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

    if args["init"]:
        # setup initial environment, download binaries
        download_initial_binaries(SWM_CACHE_DIR, config.github_mirrors)
        return
    init_complete = check_init_complete(SWM_CACHE_DIR)
    if not init_complete:
        print(
            "Warning: Initialization incomplete. Consider running 'swm init' to download missing binaries."
        )
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
        elif args["show-default"]:
            default_config = create_default_config(SWM_CACHE_DIR)
            print(omegaconf.OmegaConf.to_yaml(default_config))
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
            swm.device_manager.select(args["<query>"])
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
            device_name = swm.adb_wrapper.get_device_name(
                current_device
            )  # could fail if status is not "device", such as "fastboot"
            print("Current device name:", device_name)
            swm.set_current_device(current_device)
            swm.load_swm_on_device_db()
        else:
            raise NoDeviceError("No available device")

        if args["app"]:
            if args["search"]:
                app_id = swm.app_manager.search(index=args["index"])
                with_type = args["with-type"]
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
                limit = args.get("<count>", 10)
                limit = int(limit)
                swm.app_manager.list(most_used=limit, print_formatted=True)
            elif args["run"]:
                no_new_display = args["no-new-display"]
                query = args["<query>"]
                init_config = args["<init_config>"]
                # TODO: search with query instead
                app_id = swm.app_manager.resolve_app_query(query)
                swm.app_manager.run(
                    app_id,  # type: ignore
                    init_config=init_config,
                    new_display=not no_new_display,
                )

            elif args["config"]:
                config_name = args["<config_name>"]
                if args["list"]:
                    swm.app_manager.list_app_config(print_result=True)
                elif args["show"]:
                    swm.app_manager.show_app_config(config_name)
                elif args["show-default"]:
                    swm.app_manager.show_app_config("default")
                elif args["edit"]:
                    if config_name == "default":
                        raise ValueError("Cannot edit default config")
                    swm.app_manager.edit_app_config(config_name)
                elif args["copy"]:
                    swm.app_manager.copy_app_config(
                        args["<source_name>"], args["<target_name>"]
                    )
            elif args["list"]:
                update_cache = args[
                    "update"
                ]  # cache previous list result (alias, id), but last_used_time is always up-to-date
                with_type = args["with-type"]
                swm.app_manager.list(
                    print_formatted=True,
                    update_cache=update_cache,
                    additional_fields=dict(
                        last_used_time=args["with-last-used-time"],
                        type_symbol=with_type,
                    ),
                )
        elif args["session"]:
            if args["list"]:
                sessions = swm.session_manager.list()
                print("Session saved on device %s:" % swm.current_device)
                print("\t" + ("\n\t".join(sessions)))
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
