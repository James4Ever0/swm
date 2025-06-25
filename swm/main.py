"""SWM - Scrcpy Window Manager

Usage:
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <app_name> [<app_args>...]
  swm [options] app list [--search] [--most-used <limit>]
  swm [options] app config <app_name> (show|edit)
  swm [options] session list [--search]
  swm [options] session restore [session_name]
  swm [options] session save <session_name>
  swm [options] session delete <session_name>
  swm [options] device list [--search]
  swm [options] device select <device_id>
  swm [options] device name <device_id> <device_alias>
  swm [options] baseconfig show [--diagnostic]
  swm [options] baseconfig edit
  swm --version
  swm --help

Options:
  -h --help     Show this screen.
  --version     Show version.
  -c --config=<config_file>
                Use a config file.
  -v --verbose  Enable verbose logging.
  -d --device   Device name or ID for executing the command
"""

# TODO: multi android device support
# TODO: fzf search app/session/device and dialogs after selected the candidate

import os
import platform
import shutil
import omegaconf
import sys
import traceback
import json
import subprocess
import requests
from docopt import docopt

# from .__version__ import __version__


# note: in the future, we may use a stable version of adb and scrcpy across all platforms, download it into home directory ~/.swm
def get_system_and_architecture():
    system = platform.system()
    architecture = platform.architecture()
    # usually it is the system architecture matters, not the processor, because 64bit processor can also run 32bit binaries
    return system, architecture


# if anything goes wrong, we need to collect info on target system


def collect_system_info_for_diagnostic():
    platform_fullname = platform.platform()
    return platform_fullname


def pretty_print_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=4)


def print_diagnostic_info(program_specific_params):
    system_info = collect_system_info_for_diagnostic()
    print("System info:", system_info, sep="\n")
    print("Program parameters:", pretty_print_json(program_specific_params), sep="\n")


def execute_subprogram(program_path, args):
    try:
        subprocess.run([program_path] + args, check=True)
    except subprocess.CalledProcessError as e:
        print("Error executing subprogram:", e)


def search_or_obtain_binary_path_from_environmental_variable_or_download(
    cache_dir: str, bin_name: str
):
    # binary name should be lower case
    # on windows we need to add .exe suffix
    bin_env_name = bin_name.upper()
    bin_name = bin_name.lower()
    if platform.system() == "Windows":
        bin_name += ".exe"
    bin_path = shutil.which(bin_name)
    if bin_path is None:
        # try to obtain it from uppercase environment variable
        bin_path = os.environ.get(bin_env_name, None)
    if bin_path is None:
        # now, download the binary
        bin_path = check_and_download_binary_into_cache_dir_and_return_path(
            cache_dir, bin_name
        )
        assert bin_path is not None, (
            f"Failed to download binary '%s' (which should never happen)" % bin_name
        )
    return bin_path


def format_unsupported_binary_downloader_info(bin_name: str):
    return f"Cannot download or check binary '%s' since it is not supported" % bin_name


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
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200, response.elapsed.total_seconds()
    except:
        return False, -1


def check_binary_downloaded_in_cache_dir(cache_dir: str, bin_name: str):
    if bin_name.startswith("adb"):
        ...
    elif bin_name.startswith("scrcpy"):
        ...
    else:
        raise NotImplemented(format_unsupported_binary_downloader_info(bin_name))


def download_binary_into_cache_dir_and_return_path(cache_dir: str, bin_name: str):
    if bin_name.startswith("adb"):
        ...
    elif bin_name.startswith("scrcpy"):
        ...
    else:
        raise NotImplemented(format_unsupported_binary_downloader_info(bin_name))


def check_and_download_binary_into_cache_dir_and_return_path(
    cache_dir: str, bin_name: str, check_only=False
):
    # check if downloaded
    is_downloaded, bin_path = check_binary_downloaded_in_cache_dir(cache_dir, bin_name)

    if is_downloaded:
        return bin_path
    else:
        if check_only:
            raise Exception(
                "Failed to obtain binary path after downloaded '%s'" % bin_path
            )
        download_binary_into_cache_dir_and_return_path(cache_dir, bin_name)
        return check_and_download_binary_into_cache_dir_and_return_path(
            cache_dir, bin_name, check_only=True
        )


class SWM:
    def __init__(self, adb, scrcpy):
        self.adb = adb
        self.scrcpy = scrcpy


class AppManager:
    def __init__(self): ...
    def list(self): ...
    def run(self): ...
    def config(self): ...


class SessionManager:
    def __init__(self): ...
    def list(self): ...
    def restore(self): ...
    def save(self): ...
    def delete(self): ...


def main():
    # TODO: find out on windows if it is possible to expand '~'
    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", os.path.expanduser("~/.swm"))
    SWM_CONFIG_PATH = os.path.join(SWM_CACHE_DIR, "config.yaml")

    # TODO: use a flag or environment variable or config like USE_SWM_DOWNLOADED_BINARIES_ONLY to only use swm managed android binary dependencies
    # TODO: use swm for adb and scrcpy commands by passing the rest of arguments to the corresponding binaries (maybe for fastboot?), like "swm (adb|scrcpy|fastboot)"
    # TODO: open an editor for editing swm config

    swm_config = omegaconf.OmegaConf.load(SWM_CONFIG_PATH)

    SWM_ZOOM_FACTOR = swm_config.zoom_factor  # for current PC only

    SWM_SESSION_AUTOSAVE = (
        swm_config.session_autosave
    )  # save session everytime after executing swm command, named as "latest"

    cache_dir = SWM_CACHE_DIR

    ADB = search_or_obtain_binary_path_from_environmental_variable_or_download(
        cache_dir, "adb"
    )
    SCRCPY = search_or_obtain_binary_path_from_environmental_variable_or_download(
        cache_dir, "scrcpy"
    )

    FZF = search_or_obtain_binary_path_from_environmental_variable_or_download(
        cache_dir, "fzf"
    )  # for searching

    ANDROID_SESSION_STORAGE_PATH = (
        swm_config.android_session_storage_path
    )  # "/sdcard/swm"

    program_specific_params = {}
    GITHUB_MIRRORS = swm_config.github_mirrors

    args = parse_args()
    program_specific_params["docopt_parsed_args"] = args
    program_specific_params["sys_argv"] = sys.argv
    program_specific_params["adb"] = ADB
    program_specific_params["scrcpy"] = SCRCPY
    program_specific_params.update(
        dict(
            swm_config_path=SWM_CONFIG_PATH,
            swm_cache_dir=SWM_CACHE_DIR,
            swm_config=omegaconf.OmegaConf.to_object(swm_config),
        )
    )
    override_system_excepthook(program_specific_params)
    cli_device = args["--device"]
    # TODO: handle device passed in commandline, like "swm --device <device_id> (adb|scrcpy|app|session)", and change adb/scrcpy device accordingly
    # TODO: warn the user about the device passed in commandline is different from the one in config
    # TODO: warn the user if adb/scrcpy args has different device selected than config/commandline
    # priority: adb/scrcpy args > commandline > config
    if args["adb"]:
        execute_subprogram(ADB, args["<adb_args>"])
    elif args["scrcpy"]:
        execute_subprogram(SCRCPY, args["<scrcpy_args>"])
    elif args["--version"]:
        ...
    elif args["baseconfig"]:
        ...
        if args["show"]:
            if args["--diagnostic"]:
                # TODO: highlight/show environmental overriden patameters
                print_diagnostic_info(program_specific_params)
            else:
                ...
        elif args["edit"]:
            ...
    elif args["app"]:
        am = AppManager(device)
        if args["list"]:
            am.list()
        elif args["run"]:
            app_name = args["<app_name>"]
            app_args = args["<app_args>"]
            am.run(app_name, app_args)
        elif args["config"]:
            app_name = args["<app_name>"]
        else:
            raise ValueError("Incomplete app subcommand")
    elif args["session"]:
        sm = SessionManager(device)
        if args["list"]:
            sm.list()
        elif args["restore"]:
            sm.restore()
        elif args["save"]:
            sm.save()
        elif args["delete"]:
            sm.delete()
        else:
            raise ValueError("Incomplete session subcommand")
    else:
        raise ValueError("Undefined branch triggered by parser")


def override_system_excepthook(program_specific_params):
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        print(f"An unhandled exception occurred:")
        print(f"Type: {exc_type.__name__}")
        print(f"Value: {exc_value}")
        print_diagnostic_info(program_specific_params)

    sys.excepthook = custom_excepthook


def parse_args():
    # Main parser for 'swm'
    args = docopt(__doc__, version="SWM 0.0.1", options_first=True)

    return args

def select_adb_device(adb, default_device):
    all_devices = adb.devices()
    if len(all_devices) == 0:
        # no devices.
        return 
    elif len(all_devices) == 1:
        # only one device.
        device = all_devices[0]
    else:
        if default_device in all_devices:
            return default_device
        else:
            prompt_for_device = f"Select a device from {all_devices}"
            ...

def list_most_used_apps(limit: int): ...


def list_all_apps(): ...


def update_session_info(): ...


def restore_session(): ...


if __name__ == "__main__":
    main()
    # print("sys_argv:", sys.argv)
    # parse_args()
