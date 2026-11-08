'''The test setup itself: Django with MaRDMO, and no network.'''
import os
import socket

import pytest
from django.apps import apps
from django.db import connection
from pytest_socket import SocketBlockedError, SocketConnectBlockedError

import MaRDMO


def test_mardmo_is_installed():
    assert apps.is_installed('MaRDMO')


def test_version_comes_from_the_package():
    '''pyproject.toml reads the version from MaRDMO/__init__.py.'''
    assert MaRDMO.__version__ == MaRDMO.VERSION


@pytest.mark.filterwarnings('ignore:A test tried to use socket')
def test_network_is_blocked():
    '''With a database server in CI, only its host is allowed (--allow-hosts).'''
    with pytest.raises((SocketBlockedError, SocketConnectBlockedError)):
        socket.create_connection(('portal.mardi4nfdi.de', 443), timeout=1)


@pytest.mark.django_db
def test_database_is_the_one_asked_for():
    '''TEST_DB=postgresql or mysql must not run on SQLite unnoticed.'''
    assert connection.vendor == os.environ.get('TEST_DB', 'sqlite')
