from setuptools import Extension, setup

setup(
    name='kag-angelscript-parser',
    version='0.1.0',
    ext_modules=[Extension('kag_angelscript', ['binding.c', 'src/parser.c', 'src/scanner.c'], include_dirs=['src'])],
)
