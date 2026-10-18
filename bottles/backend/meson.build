params_file = configure_file(
    input:  'params.py',
    output:  'params.py',
    configuration: conf
)

subdir('wine')
subdir('models')
subdir('utils')
subdir('dlls')
subdir('repos')
subdir('managers')

bottles_sources = [
  '__init__.py',
  'globals.py',
  'runner.py',
  'diff.py',
  'health.py',
  'downloader.py',
  'logger.py',
  'cabextract.py',
  'state.py',
  params_file
]

python.install_sources(bottles_sources, subdir: 'bottles/backend')
