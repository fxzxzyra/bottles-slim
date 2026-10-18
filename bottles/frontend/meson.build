subdir('ui')
subdir('utils')
subdir('views')
subdir('widgets')
subdir('windows')
subdir('cli')

configure_file(
  input: 'bottles.py',
  output: 'bottles',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: ['rwxr-xr-x']
)

params_file = configure_file(
    input:  'params.py',
    output:  'params.py',
    configuration: conf
)

bottles_sources = [
  '__init__.py',
  'main.py',
  'operation.py',
  params_file,
]

python.install_sources(bottles_sources, subdir: 'bottles/frontend')
