# Windowed, one-directory distribution; external tools remain separate.
from PyInstaller.utils.hooks import collect_data_files
import os
import sys
from importlib.metadata import distribution

license_data = [('LICENSE', 'licenses'), ('THIRD_PARTY_NOTICES.md', 'licenses'), ('README.md', '.')]
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'Pillow', 'PyMuPDF', 'pypdf', 'psutil'):
    dist = distribution(package)
    for item in dist.files or []:
        name = item.name.lower()
        if '/licenses/' in str(item).lower() or name.startswith(('license', 'copying', 'notice', 'authors')):
            source = dist.locate_file(item)
            if source.is_file():
                license_data.append((str(source), f'licenses/{package}/{item.parent}'))

a = Analysis(
    ['launch.py'], pathex=[], binaries=[],
    datas=collect_data_files('mediaforge') + license_data,
    hiddenimports=['mediaforge.worker', 'mediaforge.converters.image', 'mediaforge.converters.pdf',
                   'mediaforge.converters.document', 'mediaforge.converters.media'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf',
              'PySide6.QtQml', 'PySide6.QtQuick', 'pytest'],
    noarchive=False,
)
# Qt 6 on Windows uses the OS ICU API (unversioned exports). PATH may contain
# Poppler/Conda ICU DLLs with version-suffixed exports under the same filename;
# bundling those makes QtCore fail to load. Windows 11 provides the correct ICU.
if sys.platform == 'win32':
    a.binaries = [entry for entry in a.binaries
                  if os.path.basename(entry[0]).lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MediaForge', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, icon='mediaforge/resources/mediaforge.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MediaForge')
