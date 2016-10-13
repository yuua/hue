#!/usr/bin/env python
# Licensed to Cloudera, Inc. under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  Cloudera, Inc. licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import json

from nose.plugins.skip import SkipTest
from nose.tools import assert_equal, assert_true

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from desktop.lib.conf import BoundConfig
from desktop.lib.django_test_util import make_logged_in_client
from desktop.lib.test_utils import add_to_group, grant_access
from hadoop.pseudo_hdfs4 import is_live_cluster

from libsolr.api import SolrApi


SOLR_SENTRY_SUPERUSER = 'solr'
SOLR_SENTRY_USER = 'systest'


LOG = logging.getLogger(__name__)


try:
  # App can be blacklisted
  from search.conf import SOLR_URL
  from search.models import Collection2
except:
  LOG.exception('Testing libsolr requires the search app to not be blacklisted')


try:
  from security.conf import SOLR_V2
except ImportError, e:
  SOLR_V2 = None


def is_solr_with_sentry():
  return SOLR_V2 is not None and type(SOLR_V2) == BoundConfig and SOLR_V2.get()


def get_test_username():
  if is_solr_with_sentry():
    return SOLR_SENTRY_USER
  else:
    return 'test'


class TestLibSolrWithSolr:

  @classmethod
  def setup_class(cls):

    if not is_live_cluster():
      raise SkipTest

    cls.client = make_logged_in_client(username=get_test_username(), is_superuser=False)
    cls.user = User.objects.get(username=get_test_username())
    add_to_group(get_test_username())
    grant_access(get_test_username(), "test", "libsolr")
    grant_access(get_test_username(), "test", "search")

    cls.user.is_superuser = True
    cls.user.save()

    resp = cls.client.post(reverse('search:install_examples'))
    content = json.loads(resp.content)

    cls.user.is_superuser = False
    cls.user.save()

    # If Sentry is enabled, grant privileges to the test user
    if is_solr_with_sentry():
      add_to_group(get_test_username(), groupname='systest')
      cls.superuser_client = make_logged_in_client(username=SOLR_SENTRY_SUPERUSER, is_superuser=True)
      cls.superuser_client.post('/security/api/sentry/create_role', {
        'role': json.dumps({
          'name': 'ops',
          'groups': ['systest'],
          'privileges': [
            {
              'status': 'new',
              'serverName': 'service1',
              'component': 'solr',
              'authorizables': [
                {
                  'type': 'COLLECTION',
                  'name_': 'log_analytics_demo'
                }
              ],
              'action': 'QUERY',
              'timestamp': 0,
              'grantorPrincipal': 'solr',
              'grantOption': False,
              'privilegeType': 'COLLECTION',
              'path': 'collections.log_analytics_demo',
              'indexerPath': '/indexer/#edit/log_analytics_demo'
            }
          ]
        }),
        'component': 'SOLR'
      }
    )

    assert_equal(content.get('status'), 0)

  @classmethod
  def teardown_class(cls):
    cls.user.is_superuser = False
    cls.user.save()

  def test_is_solr_cloud_mode(self):
    SolrApi(SOLR_URL.get(), self.user).collections()

  def test_query(self):
    collection = Collection2(user=self.user, name='log_analytics_demo')
    collection = json.loads(collection.get_json(self.user))

    query = {'qs': [{'q': ''}], 'fqs': [], 'start': 0}

    SolrApi(SOLR_URL.get(), self.user).query(collection['collection'], query)
