########
# Copyright (c) 2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

# flake8: noqa
# pylint: skip-file

import sys
PY2 = sys.version_info[0] == 2

if PY2:
    text_type = unicode
    from urllib2 import urlopen, URLError, Request
    from urllib import unquote
    from BaseHTTPServer import HTTPServer
    from  SimpleHTTPServer import SimpleHTTPRequestHandler
else:
    text_type = str
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    from urllib.parse import unquote
    from http.server import SimpleHTTPRequestHandler
    from http.server import HTTPServer

__all__ = [
    'PY2', 'text_type', 'unquote', 'HTTPServer', 'SimpleHTTPRequestHandler',
    'urlopen', 'URLError', 'Request',
]
