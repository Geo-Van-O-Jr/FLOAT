from PyInstaller.utils.hooks import copy_metadata

# The maintained Windows wheel exposes webrtcvad under a different distribution name.
datas = copy_metadata('webrtcvad-wheels')
hiddenimports = ['_webrtcvad']
