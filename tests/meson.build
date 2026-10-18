if get_option('tests')
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
