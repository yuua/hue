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

import json

from nose.plugins.skip import SkipTest
from nose.tools import assert_equal, assert_true, assert_false

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from desktop.lib.django_test_util import make_logged_in_client
from desktop.lib.test_utils import add_to_group, grant_access
from hadoop.pseudo_hdfs4 import is_live_cluster, get_db_prefix
from libsolr.tests import get_test_username, is_solr_with_sentry, SOLR_SENTRY_SUPERUSER
from libzookeeper.conf import ENSEMBLE

from indexer.controller import get_solr_ensemble, CollectionManagerController


def test_get_ensemble():

  clear = ENSEMBLE.set_for_testing('zoo:2181')
  try:
    assert_equal('zoo:2181/solr', get_solr_ensemble())
  finally:
    clear()


  clear = ENSEMBLE.set_for_testing('zoo:2181,zoo2:2181')
  try:
    assert_equal('zoo:2181,zoo2:2181/solr', get_solr_ensemble())
  finally:
    clear()



class TestIndexerWithSolr:

  @classmethod
  def setup_class(cls):

    if not is_live_cluster():
      raise SkipTest()

    cls.client = make_logged_in_client(username=get_test_username(), is_superuser=False)
    cls.superuser_client = make_logged_in_client(username=SOLR_SENTRY_SUPERUSER, is_superuser=True)
    cls.user = User.objects.get(username=get_test_username())
    add_to_group(get_test_username())
    grant_access(get_test_username(), "test", "indexer")
    grant_access(SOLR_SENTRY_SUPERUSER, "test", "indexer")

    cls.db = CollectionManagerController(cls.user)

    resp = cls.superuser_client.post(reverse('indexer:install_examples'))
    content = json.loads(resp.content)

    assert_equal(content.get('status'), 0, content.get('message'))

    # If Sentry is enabled, grant privileges to the test user
    if is_solr_with_sentry():
      add_to_group(get_test_username(), groupname='systest')
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
              'action': 'ALL',
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
      })

  @classmethod
  def teardown_class(cls):
    pass

  def test_is_solr_cloud_mode(self):
    assert_true(CollectionManagerController(self.user).is_solr_cloud_mode())

  def test_collection_exists(self):
    assert_false(self.db.collection_exists('does_not_exist'))

  def test_get_collections(self):
    self.db.get_collections()

  def test_create_and_delete_collection(self):
    name = get_db_prefix(name='solr') + 'test_create_collection'
    fields = [{'name': 'id', 'type': 'string'}, {'name': 'my_text', 'type': 'text_en'}]

    # We get exceptions if problems in both case there
    try:
      self.db.create_collection(name, fields, unique_key_field='id', df='my_text')
    finally:
      self.db.delete_collection(name, core=False)

  def test_collections_fields(self):
    uniquekey, fields = self.db.get_fields('log_analytics_demo')
    assert_equal('id', uniquekey)

    assert_true('protocol' in fields, fields)
    assert_true('country_code3' in fields, fields)
