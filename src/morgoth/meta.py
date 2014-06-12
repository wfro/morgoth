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

from morgoth.data.mongo_clients import MongoClients
from morgoth.metric_manager import MetricManager, NullMetricManager

import gevent
import re

import logging
logger = logging.getLogger(__name__)

__all__ = ['Meta']

class Meta(object):
    """
    This class is responsible for keeping track of various meta data for metrics
    """
    _db = MongoClients.Normal.morgoth
    _db_admin = MongoClients.Normal.admin
    _db_name = None
    _use_sharding = None
    _needs_updating = {}
    _refresh_interval = None
    _finishing = False
    _null_manager = NullMetricManager()
    """ Dict containg the meta data for each metric """
    _meta = {}
    """ Dict of patterns to the MetricManager"""
    _managers = {}


    @classmethod
    def load(cls, config):
        """
        Loads the existing meta data

        @param config: the app configuration object
        @type config: morgoth.config.Config
        """
        cls._db_name = config.mongo.database_name
        cls._use_sharding = config.mongo.use_sharding
        cls._needs_updating = {}
        cls._refresh_interval = config.get(
            ['metric_meta', 'refresh_interval'],
            60
        )

        # Load managers from conf
        for metric_set  in config.metrics:
            for pattern, conf in metric_set.items():
                cls._managers[pattern] = MetricManager(pattern, conf)

        # Load metrics from database
        for meta in cls._db.meta.find():
            metric = meta['_id']
            cls._meta[metric] = meta
            manager = cls._match_metric(metric)
            manager.add_metric(metric)
            manager.start()


    @classmethod
    def update(cls, metric, value):
        """
        Update a metrics meta data

        A metric's meta data will be only eventually consistent
        """
        if cls._finishing:
            return
        if metric not in cls._meta:
            meta = {
                '_id' : metric,
                'version': 0,
                'min' : value,
                'max' : value,
                'count' : 1,
            }
            #logger.debug("Created new meta %s" % str(meta))
            cls._meta[metric] = meta
            cls._update(metric)
        else:
            meta = cls._meta[metric]
            #logger.debug("Updating meta with new value: %s %f" % (str(meta), value))
            meta['min'] = min(meta['min'], value)
            meta['max'] = max(meta['max'], value)
            meta['count'] += 1

            if metric not in cls._needs_updating:
                cls._needs_updating[metric] = True
                gevent.spawn(cls._update_eventually, metric)
            #else:
            #    logger.debug("Metric already scheduled for update...")


    @classmethod
    def finish(cls):
        """
        Finish updating all metrics that still need updating
        """
        if not cls._finishing:
            cls._finishing = True
            while len(cls._needs_updating) > 0:
                metric = cls._needs_updating.keys()[0]
                cls._update(metric)



    @classmethod
    def flush(cls):
        """
        Flush all pending changes to the meta data
        """
        metrics = cls._needs_updating.keys()
        for metric in metrics:
            cls._update(metric)

    @classmethod
    def _update_eventually(cls, metric):
        gevent.sleep(cls._refresh_interval)
        if cls._finishing: return

    @classmethod
    def _update(cls, metric):
        """
        Perform the actual update of the meta data
        """
        if metric in cls._needs_updating:
            del cls._needs_updating[metric]
        meta = cls._meta[metric]
        # Update meta information
        success = False
        while not success:
            existing_meta = cls._db.meta.find_one({'_id': metric})
            if existing_meta is None:
                cls._init_new_metric(metric, meta)
            else:
                # Populate in memory meta with existing meta
                #logger.debug("Got existing meta %s" % str(existing_meta))
                meta['version'] = existing_meta['version']
                meta['min'] = min(existing_meta['min'], meta['min'])
                meta['max'] = max(existing_meta['max'], meta['max'])
                meta['count'] = max(existing_meta['count'], meta['count'])
            #logger.debug("Saving meta %s for metric %s"% (str(meta), metric))
            ret = cls._db.meta.update(
                {
                    '_id' : metric,
                    'version' : meta['version']
                }, {
                    '$set' : {
                        'min' : meta['min'],
                        'max' : meta['max'],
                        'count' : meta['count'],
                    },
                    '$inc' : {'version' : 1}
                })
            success = ret['updatedExisting']
            if not success:
                logger.error("The meta version changed. This should not have happend as this class controls all updates.")

    @classmethod
    def _init_new_metric(cls, metric, meta):
        """
        Initialize a new metric

        @param metric: the name of the metric
        @param meta: the metadata about the metric
        """
        cls._db.meta.insert(meta)

        manager = cls._match_metric(metric)
        manager.add_metric(metric)

        manager.start()

    @classmethod
    def _match_metric(cls, metric):
        """
        Determine which pattern matches the given metric

        @param metric: the name of the metric
        @return the MetricManager for the given metric
        """
        for pattern, manager in cls._managers.items():
            if re.match(pattern, metric):
                return manager

        # No config for the metric
        logger.warn("Metric '%s' has no matching configuration" % metric)
        return cls._null_manager

    @classmethod
    def delete_metric(cls, metric):
        logger.info('Deleting metric %s', metric)
        cls._db.metrics.remove({'metric' : metric})
        cls._db.windows.remove({'value.metric' : metric})
        cls._db.meta.remove({'_id' : metric})

