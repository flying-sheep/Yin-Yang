import json
import subprocess
import pwd
import os

from PySide6.QtCore import QLocale

from src.plugins._plugin import PluginDesktopDependent, PluginCommandline


def test_gnome_availability(command) -> bool:
    # Runs the first entry in the command list with --help
    try:
        out = subprocess.run(
            [command[0], 'get', command[2], command[3]],
            stdout=subprocess.DEVNULL
        ).stdout
        if out == f'No such schema \"{command[2]}\"':
            # in this case, you might want to run https://gist.github.com/atiensivu/fcc3183e9a6fd74ec1a283e3b9ad05f0
            # or you have to install that extension
            return False
    except FileNotFoundError:
        # if no such command is available, the plugin is not available
        return False


class System(PluginDesktopDependent):
    def __init__(self, desktop: str):
        match desktop:
            case 'kde':
                super().__init__(_Kde())
            case 'gtk':
                super().__init__(_Gnome())
            case _:
                raise ValueError('Unsupported desktop environment!')

        super().__init__(_Kde())


class _Gnome(PluginCommandline):
    name = 'System'

    # TODO allow using the default themes, not only user themes

    def __init__(self):
        super().__init__(["gsettings", "set", "org.gnome.shell.extensions.user-theme", "name", "%t"])

    @property
    def available(self) -> bool:
        return test_gnome_availability(self.command)


def get_readable_kde_theme_name(file) -> str:
    """Searches for the long_name in the file and maps it to the found short name"""

    for line in file:
        if 'Name=' in line:
            name: str = ''
            write: bool = False
            for letter in line:
                if letter == '\n':
                    write = False
                if write:
                    name += letter
                if letter == '=':
                    write = True
            return name


def get_name_key(meta):
    locale = filter(
        lambda name: name in meta['KPlugin'],
        [f'Name[{QLocale().name()}]',
         f'Name[{QLocale().language()}]',
         'Name']
    )
    return next(locale)


class _Kde(PluginCommandline):
    name = 'System'
    translations = {}

    def __init__(self):
        super().__init__(["lookandfeeltool", "-a", '%t'])
        self.theme_light = 'org.kde.breeze.desktop'
        self.theme_dark = 'org.kde.breezedark.desktop'

    def set_mode(self, dark: bool) -> bool:
        # TODO remove this once https://bugs.kde.org/show_bug.cgi?id=446074 is fixed
        if not self.enabled:
            return False

        theme = self.theme_dark if dark else self.theme_light
        return self.set_theme(theme) == theme and self.set_theme(theme) == theme

    @property
    def available_themes(self) -> dict:
        if self.translations != {}:
            return self.translations

        # aliases for path to use later on
        user = pwd.getpwuid(os.getuid())[0]
        path = "/home/" + user + "/.local/share/plasma/look-and-feel/"

        # asks the system what themes are available
        # noinspection SpellCheckingInspection
        long_names = subprocess.check_output(["lookandfeeltool", "-l"], universal_newlines=True)
        long_names = long_names.splitlines()
        long_names.sort()

        # get the actual name
        for long_name in long_names:
            # trying to get the Desktop file
            try:
                # json in newer versions
                with open(f'/usr/share/plasma/look-and-feel/{long_name}/metadata.json', 'r') as file:
                    meta = json.load(file)
                    key = get_name_key(meta)
                    self.translations[long_name] = meta['KPlugin'][key]
            except OSError:
                try:
                    # load the name from the metadata.desktop file
                    with open(f'/usr/share/plasma/look-and-feel/{long_name}/metadata.desktop', 'r') as file:
                        self.translations[long_name] = get_readable_kde_theme_name(file)
                except OSError:
                    # check the next path if the themes exist there
                    try:
                        # load the name from the metadata.desktop file
                        with open(f'{path}{long_name}/metadata.desktop', 'r') as file:
                            # search for the name
                            self.translations[long_name] = get_readable_kde_theme_name(file)
                    except OSError:
                        # if no file exist lets just use the long name
                        self.translations[long_name] = long_name

        return self.translations