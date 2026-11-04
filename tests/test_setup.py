'''The test setup itself: Django with MaRDMO, and no network.'''
import socket

import pytest
from django.apps import apps
from pytest_socket import SocketBlockedError

import MaRDMO


def test_mardmo_is_installed():
    assert apps.is_installed('MaRDMO')


def test_version_comes_from_the_package():
    '''pyproject.toml reads the version from MaRDMO/__init__.py.'''
    assert MaRDMO.__version__ == MaRDMO.VERSION


@pytest.mark.filterwarnings('ignore:A test tried to use socket')
def test_network_is_blocked():
    with pytest.raises(SocketBlockedError):
        socket.create_connection(('portal.mardi4nfdi.de', 443), timeout=1)
