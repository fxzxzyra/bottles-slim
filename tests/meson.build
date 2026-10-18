if get_option('tests')
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
  foreach group : ['backend', 'frontend', 'downstream']
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
