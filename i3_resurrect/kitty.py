from __future__ import annotations

import json
import subprocess
from pathlib import Path
from . import config

import psutil


def get_listen_socket(listen_socket: str, pid: int):
    # Handle the custom placeholder that could appear in Kitty's listen_socket
    if "{kitty_pid}" in listen_socket:
        return listen_socket.replace("{kitty_pid}", str(pid))

    # If the kitty_pid placeholder doesn't exist, Kitty will automatically
    # append -{pid} to the listen_socket
    return f"{listen_socket}-{pid}"


def get_container_tree(listen_socket: str):
    """
    Use Kitty's remote control feature to get the currently running
    subprocesses as a container tree.
    """
    try:
        output = subprocess.check_output(
            ["kitty", "@", "--to", listen_socket, "ls", "--all-env-vars"]
        ).decode("utf-8")
    except subprocess.CalledProcessError as err:
        pass
    return json.loads(output)


def get_window_subprocess_command(window):
    """
    Create the subprocess command to restore any subprocesses in the current
    window. If a subprocess is running and is configured to be saved, it will
    be saved and restored.
    """

    process = psutil.Process(window["pid"])

    shell = window["env"].get("SHELL", "bash")
    # The default launch command needs to change as a subprocess in Kitty
    # should return back to the shell after the subprocess exits
    supported_subprocesses = config.get("plugins", [])["kitty"]["subprocesses"]
    subprocess_command = ""
    for child in process.children(True):
        if child.name() in supported_subprocesses:
            cmdline = child.cmdline()
            command, args = cmdline[0], cmdline[1:]
            for arg in args:
                command += " " + arg
            subprocess_command = f"{shell} -c '{command} && {shell}'"
            return subprocess_command

    return subprocess_command


def get_window_launch_command(window) -> str:
    """
    Create a window's launch command to restore its working directory and any
    subprocesses that are running in it.
    """
    launch_command = f'launch --cwd="{window["cwd"]}"'
    subprocess_command = get_window_subprocess_command(window)
    if subprocess_command:
        launch_command += " " + subprocess_command
    # Nice addition would be the ability to pass the environment variables

    return launch_command + "\n"


def parse_tree_to_session(tree) -> str:
    """
    Parse a Kitty container tree into a session that can be used to restore the
    exact layout and programs that this kitty terminal is running.
    """

    output = ""
    for tab in tree["tabs"]:
        output += "new_tab\n"
        output += f"layout {tab['layout']}\n"

        if tab["is_active"]:
            output += "focus\n"

        for window in tab["windows"]:
            output += get_window_launch_command(window)

    return output


def create_session_file(container_tree, directory, pid) -> Path:
    """
    Create a session file for the container. The session file will be written
    under i3_PATH in the format kitty-session-{container.window_id}.
    """

    session_contents = parse_tree_to_session(container_tree[0])

    session_file = directory / f"kitty-session-{pid}"

    with session_file.open("w") as f:
        f.write(session_contents)

    return str(session_file)


def save_kitty_session(pid, directory) -> None:

    listen_socket = get_listen_socket(
        config.get("plugins", [])["kitty"]["listen_socket"],
        pid
    )
    container_tree = get_container_tree(listen_socket)
    session_file = create_session_file(container_tree, directory, pid)

    return session_file
