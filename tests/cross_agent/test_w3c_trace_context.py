import json
import os
import pytest
import webtest
from newrelic.packages import six

from newrelic.api.transaction import current_transaction
from newrelic.api.wsgi_application import wsgi_application
from newrelic.common.object_wrapper import transient_function_wrapper
from testing_support.validators.validate_span_events import (
        validate_span_events)
from testing_support.fixtures import (override_application_settings,
        validate_transaction_metrics, validate_transaction_event_attributes,
        validate_attributes)

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
JSON_DIR = os.path.normpath(os.path.join(CURRENT_DIR, 'fixtures',
    'distributed_tracing'))

_parameters_list = ('test_name', 'trusted_account_key', 'account_id',
        'web_transaction', 'raises_exception', 'force_sampled_true',
        'span_events_enabled', 'transport_type', 'inbound_headers',
        'outbound_payloads', 'intrinsics', 'expected_metrics')

_parameters = ','.join(_parameters_list)


def load_tests():
    result = []
    path = os.path.join(JSON_DIR, 'trace_context.json')
    with open(path, 'r') as fh:
        tests = json.load(fh)

    for test in tests:
        values = (test.get(param, None) for param in _parameters_list)
        param = pytest.param(*values, id=test.get('test_name'))
        result.append(param)

    return result


@wsgi_application()
def target_wsgi_application(environ, start_response):
    transaction = current_transaction()

    if not environ['.web_transaction']:
        transaction.background_task = True

    if environ['.raises_exception']:
        try:
            raise ValueError("oops")
        except:
            transaction.record_exception()

    if '.inbound_headers' in environ:
        transaction.accept_distributed_trace_headers(
            environ['.inbound_headers'],
            transport_type=environ['.transport_type'],
        )

    payloads = []
    for _ in range(environ['.outbound_calls']):
        payloads.append([])
        transaction.insert_distributed_trace_headers(payloads[-1])

    start_response('200 OK', [('Content-Type', 'application/json')])
    return [json.dumps(payloads).encode('utf-8')]


test_application = webtest.TestApp(target_wsgi_application)


def override_compute_sampled(override):
    @transient_function_wrapper('newrelic.core.adaptive_sampler',
            'AdaptiveSampler.compute_sampled')
    def _override_compute_sampled(wrapped, instance, args, kwargs):
        if override:
            return True
        return wrapped(*args, **kwargs)
    return _override_compute_sampled


@pytest.mark.parametrize(_parameters, load_tests())
def test_trace_context(test_name, trusted_account_key, account_id,
        web_transaction, raises_exception, force_sampled_true,
        span_events_enabled, transport_type, inbound_headers,
        outbound_payloads, intrinsics, expected_metrics):

    # Prepare assertions
    if not intrinsics:
        intrinsics = {}

    common = intrinsics.get('common', {})
    common_required = common.get('expected', [])
    common_forgone = common.get('unexpected', [])
    common_exact = common.get('exact', {})

    txn_intrinsics = intrinsics.get('Transaction', {})
    txn_event_required = {'agent': [], 'user': [],
            'intrinsic': txn_intrinsics.get('expected', [])}
    txn_event_required['intrinsic'].extend(common_required)
    txn_event_forgone = {'agent': [], 'user': [],
            'intrinsic': txn_intrinsics.get('unexpected', [])}
    txn_event_forgone['intrinsic'].extend(common_forgone)
    txn_event_exact = {'agent': {}, 'user': {},
            'intrinsic': txn_intrinsics.get('exact', {})}
    txn_event_exact['intrinsic'].update(common_exact)

    override_settings = {
        'distributed_tracing.enabled': True,
        'distributed_tracing.format': 'w3c',
        'span_events.enabled': span_events_enabled,
        'account_id': account_id,
        'trusted_account_key': trusted_account_key,
    }

    extra_environ = {
        '.web_transaction': web_transaction,
        '.raises_exception': raises_exception,
        '.transport_type': transport_type,
        '.outbound_calls': outbound_payloads and len(outbound_payloads) or 0,
    }

    inbound_headers = inbound_headers and inbound_headers[0] or None
    if transport_type != 'HTTP':
        extra_environ['.inbound_headers'] = inbound_headers
        inbound_headers = None
    elif six.PY2 and inbound_headers:
        inbound_headers = {
                k.encode('utf-8'): v.encode('utf-8')
                for k, v in inbound_headers.items()}

    @validate_transaction_metrics(test_name,
            group="Uri",
            rollup_metrics=expected_metrics,
            background_task=not web_transaction)
    @validate_transaction_event_attributes(
            txn_event_required, txn_event_forgone, txn_event_exact)
    @validate_attributes('intrinsic', common_required, common_forgone)
    @override_application_settings(override_settings)
    @override_compute_sampled(force_sampled_true)
    def _test():
        return test_application.get(
            '/' + test_name,
            headers=inbound_headers,
            extra_environ=extra_environ,
        )

    if 'Span' in intrinsics:
        span_intrinsics = intrinsics.get('Span')
        span_expected = span_intrinsics.get('expected', [])
        span_expected.extend(common_required)
        span_unexpected = span_intrinsics.get('unexpected', [])
        span_unexpected.extend(common_forgone)
        span_exact = span_intrinsics.get('exact', {})
        span_exact.update(common_exact)

        _test = validate_span_events(exact_intrinsics=span_exact,
            expected_intrinsics=span_expected,
            unexpected_intrinsics=span_unexpected)(_test)
    elif not span_events_enabled:
        _test = validate_span_events(count=0)(_test)

    response = _test()
    assert response.status == '200 OK'
