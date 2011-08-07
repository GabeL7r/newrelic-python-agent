"""This module provides class types used in the construction of the raw
transaction trace hierarchy from which metrics are then to be generated.

The higher level instrumentation layer will construct a tree for each web
transaction or background task. The root node should be an instance of the
TransactionNode class. This would be passed to the agent core via the
record_transaction() method of the Agent class instance which in turn gets
passed to the process_raw_transaction() function of this module. In
processing to generic metric data, each node and its children would in turn
be processed as necessary. The base metric data would then be injected
into the application object.

For a TransactionNode the 'type' attribute will be either 'WebTransaction'
or 'OtherTransaction' corresponding to a web transaction or background task.

The 'group' attribute of both TransactionNode and FunctionNode can consist
of multiple path segments representing a primary category and any sub
categories to which the transaction is being associated. For example:

    Uri
    Function
    Script/Import
    Script/Execute
    Template/Compile
    Template/Render

The 'name' attribute is then the actual name being associated with the web
transaction, background task or function trace node.

The final composite metric path for a transaction may then be as example:

    WebTransaction/Uri/some/url
    WebTransaction/Function/module:class.function

    OtherTransaction/Script/Import//absolute/path/to/some/module.py
    OtherTransaction/Script/Import/relative/path/to/some/module.py

The rule for constructing the metric path for a transaction is:

    if group == 'Uri' and name[:1] == '/':
        path = '%s/%s%s' % (type, group, name)
    else:
        path = '%s/%s/%s' % (type, group, name)

The special case for 'Uri' with a leading slash on name is necessary to
maintain compatibility with how existing agents and core application appear
to behave.

The 'type' and 'group' attributes are separate to allow easier construction
of rollup and apdex metrics based on the categories/sub categories.

For a function trace node the final composite metric path may be:

    Function/module:class.function
    Template/Render//absolute/path/to/template.py
    Template/Render/relative/path/to/template.py

The rule for construction the metric path for a function trace node is:

    path = '%s/%s' % (group, name)

"""

import collections

import newrelic.core.metric

DatabaseNode = collections.namedtuple('DatabaseNode',
        ['database_module', 'connect_params', 'sql', 'children',
        'start_time', 'end_time', 'duration', 'exclusive',
        'stack_trace'])

ExternalNode = collections.namedtuple('ExternalNode',
        ['library', 'url', 'children', 'start_time', 'end_time',
        'duration', 'exclusive'])

FunctionNode = collections.namedtuple('FunctionNode',
        ['group', 'name', 'children', 'start_time', 'end_time',
        'duration', 'exclusive'])

MemcacheNode = collections.namedtuple('MemcacheNode',
        ['command', 'children', 'start_time', 'end_time', 'duration',
        'exclusive'])

ErrorNode = collections.namedtuple('ErrorNode',
        ['type', 'message', 'stack_trace', 'custom_params',
        'file_name', 'line_number', 'source'])

_TransactionNode = collections.namedtuple('_TransactionNode',
        ['type', 'group', 'name', 'request_uri', 'response_code',
        'request_params', 'custom_params', 'queue_start', 'start_time',
        'end_time', 'duration', 'exclusive', 'children', 'errors',
        'slow_sql', 'apdex_t', 'ignore_apdex'])

class TransactionNode(_TransactionNode):

    """Class holding data corresponding to the root of the transaction. All
    the nodes of interest recorded for the transaction are held as a tree
    structure within the 'childen' attribute. Errors raised can recorded
    are within the 'errors' attribute. Nodes corresponding to slow SQL
    requests are available directly in the 'slow_sql' attribute.

    """

    def metric_name(self, type=None):
        type = type or self.type

	# Stripping the leading slash on the request URL held by
	# name when type is 'Uri' is to keep compatibility with
	# PHP agent and also possibly other agents. Leading
	# slash it not deleted for other category groups as the
	# leading slash may be significant in that situation.

        if self.group == 'Uri' and self.name[:1] == '/':
            path = '%s/%s%s' % (self.type, self.group, self.name)
        else:
            path = '%s/%s/%s' % (self.type, self.group, self.name)

        return path

    def time_metrics(self):
        """Return a generator yielding the timed metrics for this node.

        """

	# TODO What to do about a transaction where the name is
	# None. In the PHP agent it replaces it with an
	# underscore for timed metrics and continues. For an
	# apdex metric the PHP agent ignores it however. For now
	# we just ignore it.

        if not self.name:
            return

        if self.type == 'WebTransaction':
	    # Report time taken by request dispatcher. We don't
	    # know upstream time distinct from actual request
	    # time so can't report time exclusively in the
	    # dispatcher.

            # TODO Technically could work this out with the
            # modifications in Apache/mod_wsgi to mark start of
            # the request. How though does that differ to queue
            # time. Need to clarify purpose of HttpDispatcher
            # and how the exclusive component would appear in
            # the overview graphs.

            yield newrelic.core.metric.TimeMetric(name='HttpDispatcher',
                    scope='', overflow=None, forced=False,
                    duration=self.duration, exclusive=0)

            # Upstream queue time within any web server front end.

            # TODO How is this different to the exclusive time
            # component for the dispatcher above.

            # TODO Not yet dealing with additional headers for
            # tracking time through multiple front ends.

            if self.queue_start != 0:
                queue_wait = self.start_time = self.queue_start
                if queue_wait < 0:
                    queue_wait = 0

                yield newrelic.core.metric.TimeMetric(
                        name='WebFrontend/QueueTime', scope='',
                        overflow=None, forced=True, duration=queue_wait,
                        exclusive=0)

	# Generate the full transaction metric.

        name = self.metric_name()

        yield newrelic.core.metric.TimeMetric(name=name, scope=None,
                overflow=None, forced=True, duration=self.duration,
                exclusive=self.exclusive)

        # Generate the rollup metric.

        if self.type != 'WebTransaction':
            rollup = '%s/all' % self.type
        else:
            rollup = self.type

        yield newrelic.core.metric.TimeMetric(name=rollup, scope=None,
                overflow=None, forced=True, duration=self.duration,
                exclusive=self.exclusive)

    def apdex_metrics(self):
        """Return a generator yielding the apdex metrics for this node.

        """

        if not self.name:
            return

        if self.ignore_apdex:
            return

        # The apdex metrics are only relevant to web transactions.

        if self.type != 'WebTransaction':
            return

	# The magic calculations based on apdex_t. The apdex_t
	# is based on what was in place at the start of the
	# transaction. This could have changed between that
	# point in the request and now.

        satisfying = 0
        tolerating = 0
        frustrating = 0

        if self.errors:
            frustrating = 1
        else:
            if self.duration <= self.apdex_t:
                satisfying = 1
            elif self.duration <= 4 * self.apdex_t:
                tolerating = 1
            else:
                frustrating = 1

        # Generate the full apdex metric. In this case we
        # need to specific an overflow metric for case where
        # too many metrics have been generated and want to
        # stick remainder in a bucket.

	# TODO Should the apdex metric path only include the
	# first segment of group? That is, only the top level
	# category and not any sub categories.

        name = self.metric_name('Apdex')
        overflow = 'Apdex/%s/*' % self.group

        yield newrelic.core.metric.ApdexMetric(name=name, scope='',
                overflow=overflow, forced=False, satisfying=satisfying,
                tolerating=tolerating, frustrating=frustrating)

        # Generate the rollup metric.

        yield newrelic.core.metric.ApdexMetric(name='Apdex', scope='',
                overflow=None, forced=True, satisfying=satisfying,
                tolerating=tolerating, frustrating=frustrating)
