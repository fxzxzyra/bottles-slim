bottles_sources = [
  '__init__.py',
  'utils.py',
]

python.install_sources(bottles_sources, subdir: 'bottles/frontend/cli')

configure_file(
  input: 'cli.py',
  output: 'bottles-cli',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: ['rwxr-xr-x']
)
