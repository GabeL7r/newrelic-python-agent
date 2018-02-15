import sys
import pytest

from newrelic.api.transaction import current_transaction
from newrelic.api.background_task import background_task


@pytest.fixture()
def future_arg(request):
    # Avoid importing asyncio until after the instrumentation hooks are set up
    import asyncio

    loop = asyncio.get_event_loop()

    @asyncio.coroutine
    def _coro(txn):
        try:
            assert current_transaction() is txn
            yield
            assert current_transaction() is txn
        finally:
            loop.stop()

    arg_type = request.getfixturevalue('arg_type')

    if arg_type == 'future':
        future = asyncio.Future()
        future.add_done_callback(lambda f: loop.stop())
        future.set_result(True)
        return lambda txn: future
    elif arg_type == 'coroutine':
        return _coro
    elif arg_type == 'awaitable':
        from _async_coroutine import awaitable
        return awaitable
    else:
        raise ValueError('Unrecognized argument type for ensure_future')


arg_types = ['future', 'coroutine']
if sys.version_info >= (3, 5):
    arg_types.append('awaitable')


@pytest.mark.parametrize('arg_type', arg_types)
@pytest.mark.parametrize('explicit_loop', [True, False])
@pytest.mark.parametrize('in_transaction', [True, False])
def test_ensure_future(explicit_loop, arg_type, future_arg, in_transaction):
    def _test():
        # Avoid importing asyncio until after the instrumentation hooks are set
        # up
        import asyncio
        if hasattr(asyncio, 'ensure_future'):
            ensure_future = asyncio.ensure_future
        else:
            ensure_future = asyncio.async

        loop = asyncio.get_event_loop()

        @asyncio.coroutine
        def timeout():
            yield from asyncio.sleep(2.0)
            loop.stop()
            raise TimeoutError("Test timed out")

        timeout_future = ensure_future(timeout())

        kwargs = {}
        if explicit_loop:
            kwargs['loop'] = loop

        txn = current_transaction()

        # Call ensure future prior to dropping the transaction
        task = ensure_future(future_arg(txn), **kwargs)

        # Drop the transaction explicitly.
        if in_transaction:
            txn.drop_transaction()

        try:
            loop = asyncio.get_event_loop()

            # This should run the coroutine until it calls stop
            loop.run_forever()

            # Cancel the timeout
            timeout_future.cancel()

            # Cause any exception to be reraised here
            task.result()
        finally:
            # Put the transaction back prior to transaction __exit__
            # Since transaction __exit__ calls drop_transaction, the
            # transaction is expected to be in the transaction cache
            if in_transaction:
                txn.save_transaction()

    if in_transaction:
        background_task(name='test_ensure_future')(_test)()
    else:
        _test()
