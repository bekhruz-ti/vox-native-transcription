# Overrides the bundled PyInstaller hook, which hardcodes copy_metadata('webrtcvad').
# On Python 3.12+ the only installable build is the `webrtcvad-wheels` distribution,
# which ships the same `webrtcvad` module under a different distribution name.
from PyInstaller.utils.hooks import copy_metadata

try:
    datas = copy_metadata("webrtcvad")
except Exception:
    datas = copy_metadata("webrtcvad-wheels")
