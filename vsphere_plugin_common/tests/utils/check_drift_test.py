from mock import Mock
from pytest import fixture
from cloudify.state import current_ctx
from ...utils import check_drift

import logging


@fixture
def ctx():
    ctx = Mock()
    ctx.instance = Mock(runtime_properties={})
    current_ctx.set(ctx)
    yield ctx
    current_ctx.clear()


def get_logger(debug):
    logger = logging.getLogger('check_drift_test')
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logging.captureWarnings(not debug)

    output_handler = logging.StreamHandler()
    # We'll handle the actual logging level in the logger itself
    output_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(message)s')
    output_handler.setFormatter(formatter)
    logger.addHandler(output_handler)
    return logger


def test_check_drift1(ctx):
    logger = get_logger(True)
    expected_configuration = {"a": "a"}
    current_configuration = {"a": "a"}
    assert check_drift(logger, expected_configuration,
                       current_configuration) == {}


def test_check_drift2(ctx):
    logger = get_logger(True)
    expected_configuration = {"a": "b"}
    current_configuration = {"a": "a"}
    assert check_drift(logger, expected_configuration,
                       current_configuration) != {}
