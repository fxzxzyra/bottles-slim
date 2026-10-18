pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name(), 'resources')
system_runners_dir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name(), 'runners')
python = import('python').find_installation('python3', pure: true)
pythondir = python.get_install_dir()

conf = configuration_data()
conf.set('PYTHON', python.full_path())
conf.set('BASE_ID', BASE_ID)
conf.set('APP_ID', APP_ID)
conf.set('APP_NAME', APP_NAME)
conf.set('APP_VERSION', APP_VERSION)
conf.set('APP_MAJOR_VERSION', APP_MAJOR_VERSION)
conf.set('APP_MINOR_VERSION', APP_MINOR_VERSION)
conf.set('PROFILE', PROFILE)
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)
conf.set('pythondir', pythondir)
conf.set('system_runners_dir', system_runners_dir)

subdir('backend')
subdir('frontend')
subdir('fvs')

bottles_sources = [
  '__init__.py',
]

python.install_sources(bottles_sources, subdir: 'bottles')
