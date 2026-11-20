from unittest import mock

import pytest

from httpie.status import ExitStatus
from .utils import MockEnvironment, http, HTTP_OK


@pytest.mark.parametrize('patch_target', [
    pytest.param('httpie.cli.definition.parser.parse_args', id='during_arg_parsing'),
    pytest.param('httpie.core.program', id='in_program'),
])
def test_keyboard_interrupt_exit_status(httpbin, patch_target):
    with mock.patch(patch_target, side_effect=KeyboardInterrupt()):
        r = http('GET', httpbin + '/get', tolerate_error_exit_status=True)
        assert r.exit_status == ExitStatus.ERROR_CTRL_C
        assert r.stderr == '\n'


def test_nested_json_syntax_error_exit_status():
    r = http('--offline', 'example.org', 'foo[bar=1',
             tolerate_error_exit_status=True)
    assert r.exit_status == ExitStatus.ERROR
    assert r.stderr.startswith('HTTPie Syntax Error: ')
    assert r.stderr.endswith('\n')


# Track A precondition for CA-1 (= CB-2): pin the `--traceback` re-raise
# paths and the `SystemExit` code handling in both phases of `raw_main`
# (base lines 89, 95, 107 and 113 were not covered by any test).
RAW_MAIN_PHASES = {
    'during_arg_parsing': 'httpie.cli.definition.parser.parse_args',
    'in_program': 'httpie.core.program',
}
INTERRUPTIONS = [
    pytest.param(KeyboardInterrupt, ExitStatus.ERROR_CTRL_C, '\n', id='ctrl_c'),
    pytest.param(lambda: SystemExit(2), ExitStatus.ERROR, '\n', id='exit_2'),
    pytest.param(lambda: SystemExit(None), ExitStatus.ERROR, '\n', id='exit_none'),
    pytest.param(lambda: SystemExit(0), ExitStatus.SUCCESS, '', id='exit_0'),
]


def run_main_capturing(*args):
    """Run `core.main()` offline; return (exit status, re-raised exception, stderr)."""
    from httpie.core import main
    env = MockEnvironment()
    status = raised = None
    with mock.patch('httpie.core.check_updates'):
        try:
            status = main(args=['http', *args, 'example.org'], env=env)
        except BaseException as e:
            raised = e
    env.stderr.seek(0)
    return status, raised, env.stderr.read()


@pytest.mark.parametrize('phase', RAW_MAIN_PHASES)
@pytest.mark.parametrize('make_exc, expected_status, expected_stderr', INTERRUPTIONS)
@pytest.mark.parametrize('traceback', [False, True], ids=['plain', 'traceback'])
def test_interruption_handling(phase, make_exc, expected_status, expected_stderr, traceback):
    exc = make_exc()
    with mock.patch(RAW_MAIN_PHASES[phase], side_effect=exc):
        status, raised, stderr = run_main_capturing(*(['--traceback'] if traceback else []))
    if traceback and expected_status != ExitStatus.SUCCESS:
        assert raised is exc  # the very same exception object propagates
    else:
        assert raised is None
        assert status == expected_status
    assert stderr == expected_stderr


def test_ok_response_exits_0(httpbin):
    r = http('GET', httpbin + '/get')
    assert HTTP_OK in r
    assert r.exit_status == ExitStatus.SUCCESS


def test_error_response_exits_0_without_check_status(httpbin):
    r = http('GET', httpbin + '/status/500')
    assert '500 INTERNAL SERVER ERROR' in r
    assert r.exit_status == ExitStatus.SUCCESS
    assert not r.stderr


def test_timeout_exit_status(httpbin):

    r = http('--timeout=0.01', 'GET', httpbin + '/delay/0.5',
             tolerate_error_exit_status=True)
    assert r.exit_status == ExitStatus.ERROR_TIMEOUT


def test_3xx_check_status_exits_3_and_stderr_when_stdout_redirected(
        httpbin):
    env = MockEnvironment(stdout_isatty=False)
    r = http('--check-status', '--headers',
             'GET', httpbin + '/status/301',
             env=env, tolerate_error_exit_status=True)
    assert '301 MOVED PERMANENTLY' in r
    assert r.exit_status == ExitStatus.ERROR_HTTP_3XX
    assert '301 moved permanently' in r.stderr.lower()


def test_3xx_check_status_redirects_allowed_exits_0(httpbin):
    r = http('--check-status', '--follow',
             'GET', httpbin + '/status/301',
             tolerate_error_exit_status=True)
    # The redirect will be followed so 200 is expected.
    assert HTTP_OK in r
    assert r.exit_status == ExitStatus.SUCCESS


def test_4xx_check_status_exits_4(httpbin):
    r = http('--check-status', 'GET', httpbin + '/status/401',
             tolerate_error_exit_status=True)
    assert '401 UNAUTHORIZED' in r
    assert r.exit_status == ExitStatus.ERROR_HTTP_4XX
    # Also stderr should be empty since stdout isn't redirected.
    assert not r.stderr


def test_5xx_check_status_exits_5(httpbin):
    r = http('--check-status', 'GET', httpbin + '/status/500',
             tolerate_error_exit_status=True)
    assert '500 INTERNAL SERVER ERROR' in r
    assert r.exit_status == ExitStatus.ERROR_HTTP_5XX
