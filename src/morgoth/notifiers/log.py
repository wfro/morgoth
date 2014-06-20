#
# Copyright 2014 Nathaniel Cook
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from morgoth.notifiers.notifier import Notifier

import logging
logger = logging.getLogger(__name__)

class LogNotifier(Notifier):
    """
    Simply logs the occurence of anomaly
    """
    def __init__(self, app, level):
        super(LogNotifier, self).__init__(app)
        self._level = getattr(logging, level.upper())

    @classmethod
    def from_conf(cls, conf, app):
        """
        Create a notifier from the given conf

        @param conf: a conf object
        """
        return LogNotifier(app, conf.get('level', 'INFO'))


    def notify(self, metric, windows):
        """
        Notify that the window is anomalous
        """
        logger.log(self._level, "Window: %s is anomalous as determined by %s", metric, windows)
