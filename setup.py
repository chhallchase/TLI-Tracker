from distutils.core import setup
import py2exe
options = {
    'py2exe': {
        'includes': ['win32gui', 'win32process', 'tkinter', 'psutil', 're', 'json']
    }
}

setup(
    version="0.0.1a4",
    options=options,
    description="TorchFurry Torchlight Income Statistics Tool - English Version",
    console=['index_english.py'],
    data_files=[('',['full_table.json',"update_log.txt","instructions.txt"])]
)