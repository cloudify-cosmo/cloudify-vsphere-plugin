import glob
import os
import string
import subprocess

pytest_plugins = (
    'cloudify_tester.steps',
    'cloudify_tester.fixtures',
    'helpers.steps',
)


def pytest_ignore_collect(path, config):
    path = path.dirname
    parent_dir, current_dir = os.path.split(path)
    parent_dir = os.path.split(parent_dir)[1]
    if current_dir == 'generated_features' and parent_dir == 'system_tests':
        return False
    else:
        # Ignore anything not in system_tests/generated_features
        return True


# TODO: Find a way to work around pytest's idiocy so this works imported or
# in a plugin
def pytest_configure(config):
    base_path = os.path.split(__file__)[0]

    feature_files_path = os.path.join(
        base_path,
        'features',
    )

    generated_features_path = os.path.join(
        base_path,
        'generated_features',
    )
    init_path = os.path.join(
        generated_features_path,
        '__init__.py',
    )

    subprocess.check_call(['rm', '-rf', generated_features_path])
    os.mkdir(generated_features_path)
    with open(init_path, 'w') as init_handle:
        init_handle.write('')

    feature_number = 0
    for feature_file in glob.glob(os.path.join(
        feature_files_path, '*.feature'
    )):
        feature_name = os.path.split(feature_file)[1][:-len('.feature')]
        clean_feature_name = ''
        for char in feature_name:
            if char in string.ascii_letters + string.digits:
                next_char = char
            else:
                next_char = '_'
            clean_feature_name += next_char
        feature_module_name = 'test_{}_{}'.format(feature_number,
                                                  clean_feature_name)
        feature_module_py = '{}.py'.format(feature_module_name)
        generated_feature_path = os.path.join(
            generated_features_path,
            feature_module_py,
        )

        feature = """from pytest_bdd import scenarios

scenarios('{}')""".format(os.path.join(feature_files_path, feature_file))

        with open(generated_feature_path, 'w') as feature_handle:
            feature_handle.write(feature)

        feature_number += 1

    config.args.append(generated_features_path)
