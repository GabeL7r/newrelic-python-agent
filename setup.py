from distutils.core import setup, Extension
import sys

from distutils import sysconfig
dummy = sysconfig.get_config_vars('CFLAGS', 'OPT')
sysconfig._config_vars['CFLAGS'] = sysconfig._config_vars['CFLAGS'].replace(
  ' -Os ', ' ')
sysconfig._config_vars['OPT'] = sysconfig._config_vars['OPT'].replace(
  ' -Os ', ' ')

sources = [
  "php_agent/application.c",
  "php_agent/daemon_protocol.c",
  "php_agent/genericobject.c",
  "php_agent/globals.c",
  "php_agent/harvest.c",
  "php_agent/logging.c",
  "php_agent/metric_table.c",
  "php_agent/nrbuffer.c",
  "php_agent/nrthread.c",
  "php_agent/samplers.c",
  "php_agent/stringpool.c",
  "php_agent/utils.c",
  "php_agent/web_transaction.c",
  "php_agent/wt_error.c",
  "php_agent/wt_external.c",
  "php_agent/wt_function.c",
  "php_agent/wt_memcache.c",
  "php_agent/wt_params.c",
  "php_agent/wt_sql.c",
  "php_agent/wt_utils.c",
  "wrapper/_newrelicmodule.c",
  "wrapper/py_application.c",
  "wrapper/py_background_task.c",
  "wrapper/py_database_trace.c",
  "wrapper/py_error_trace.c",
  "wrapper/py_external_trace.c",
  "wrapper/py_function_trace.c",
  "wrapper/py_import_hook.c",
  "wrapper/py_in_function.c",
  "wrapper/py_memcache_trace.c",
  "wrapper/py_out_function.c",
  "wrapper/py_post_function.c",
  "wrapper/py_pre_function.c",
  "wrapper/py_settings.c",
  "wrapper/py_transaction.c",
  "wrapper/py_utilities.c",
  "wrapper/py_web_transaction.c",
]

define_macros = []
define_macros.append(('NEWRELIC_AGENT_LANGUAGE', '"python"'))
define_macros.append(('HAVE_CONFIG_H', '1'))

if sys.version_info[:2] < (2, 5):
    define_macros.append(('Py_ssize_t', 'int'))

extension = Extension(
  name = "_newrelic",
  sources = sources,
  define_macros = define_macros,
  include_dirs = ['.', 'php_agent'],
)

setup(
  name = "newrelic",
  description = "Python agent for NewRelic RPM",
  url = "http://www.newrelic.com",
  packages = ['newrelic'],
  ext_modules = [extension],
)
