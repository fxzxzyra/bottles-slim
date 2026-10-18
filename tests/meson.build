if get_option('tests')
  add_test_setup('installed', env: {
    'BOTTLES_TEST_PACKAGE_ROOT': pythondir,
    'BOTTLES_TEST_RESOURCE': pkgdatadir / 'bottles.gresource',
    'BOTTLES_TEST_DATA_RESOURCE': pkgdatadir / 'data.gresource',
    'BOTTLES_TEST_LOCALEDIR': get_option('prefix') / get_option('localedir'),
    'GSETTINGS_SCHEMA_DIR': get_option('prefix') / get_option('datadir') / 'glib-2.0/schemas',
  })
  test(
    'Installed application layout', python,
    args: [
      files('installation.py')[0], meson.project_build_root(),
      pythondir, get_option('prefix') / get_option('datadir'),
    ],
    suite: 'installation',
    depends: [bottles_resources, data_resources, test_schemas],
    is_parallel: false,
    timeout: 300,
  )
  test_dependencies = run_command(
    python, files('run.py')[0], '--check-dependencies',
    check: false,
  )
  if test_dependencies.returncode() != 0
    error(
      'Test dependencies are unavailable in ' + python.full_path() + ': ' +
      test_dependencies.stdout().strip() + '\n' + test_dependencies.stderr().strip() +
      '\nPrepare requirements.txt, requirements.dev.txt and GI typelibs in this interpreter, or select a prepared interpreter with -Dpython_interpreter=/absolute/path/to/python.',
    )
  endif
  find_program('xvfb-run', required: true)
  find_program('dbus-run-session', required: true)
  foreach group : ['backend', 'frontend', 'fvs', 'downstream']
    test(
      'Python ' + group,
      python,
      args: [
        files('run.py')[0],
        '--group', group,
        '--build-root', meson.project_build_root(),
      ],
      suite: group,
      depends: [bottles_resources, data_resources, test_schemas],
      timeout: 1800,
      is_parallel: false,
    )
  endforeach
endif
