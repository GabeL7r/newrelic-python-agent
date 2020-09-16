# Copyright 2010 New Relic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from newrelic.api.database_trace import (
    DatabaseTrace,
    enable_datastore_instance_feature,
    register_database_client,
)
from newrelic.api.function_trace import FunctionTrace
from newrelic.common.object_wrapper import ObjectProxy, wrap_function_wrapper


class PostgresApi(object):
    @staticmethod
    def _instance_info(addr, connected_fut, con_params, *args, **kwargs):
        if isinstance(addr, str):
            host = "localhost"
            port = addr
        else:
            host, port = addr

        return (host, port, con_params.database)

    @classmethod
    def instance_info(cls, args, kwargs):
        return cls._instance_info(*args, **kwargs)


register_database_client(
    PostgresApi,
    "Postgres",
    quoting_style="single+dollar",
    instance_info=PostgresApi.instance_info,
)
enable_datastore_instance_feature(PostgresApi)
ROLLUP = ('Datastore/all', 'Datastore/%s/all' % PostgresApi._nr_database_product)


class ProtocolProxy(ObjectProxy):
    async def bind_execute(self, state, *args, **kwargs):
        with DatabaseTrace(
            state.query,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.bind_execute(state, *args, **kwargs)

    async def bind_execute_many(self, state, *args, **kwargs):
        with DatabaseTrace(
            state.query,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.bind_execute_many(state, *args, **kwargs)

    async def bind(self, state, *args, **kwargs):
        with DatabaseTrace(
            state.query,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.bind(state, *args, **kwargs)

    async def execute(self, state, *args, **kwargs):
        with DatabaseTrace(
            state.query,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.execute(state, *args, **kwargs)

    async def query(self, query, *args, **kwargs):
        with DatabaseTrace(
            query,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.query(query, *args, **kwargs)

    async def prepare(self, stmt_name, query, *args, **kwargs):
        with DatabaseTrace(
            "PREPARE {stmt_name} FROM '{query}'".format(
                stmt_name=stmt_name, query=query
            ),
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.prepare(stmt_name, query, *args, **kwargs)

    async def copy_in(self, copy_stmt, *args, **kwargs):
        with DatabaseTrace(
            copy_stmt,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.copy_in(copy_stmt, *args, **kwargs)

    async def copy_out(self, copy_stmt, *args, **kwargs):
        with DatabaseTrace(
            copy_stmt,
            dbapi2_module=PostgresApi,
            connect_params=getattr(self, "_nr_connect_params", None),
        ):
            return await self.__wrapped__.copy_out(copy_stmt, *args, **kwargs)


def proxy_protocol(wrapped, instance, args, kwargs):
    proxy = ProtocolProxy(wrapped(*args, **kwargs))
    proxy._nr_connect_params = (args, kwargs)
    return proxy


def wrap_connect(wrapped, instance, args, kwargs):
    trace = FunctionTrace(name='asyncpg_connect', terminal=True, rollup=ROLLUP)
    with trace:
        return wrapped(*args, **kwargs)


def instrument_asyncpg_protocol(module):
    wrap_function_wrapper(module, "Protocol", proxy_protocol)


def instrument_asyncpg_connect_utils(module):
    wrap_function_wrapper(module, '_connect', wrap_connect)
