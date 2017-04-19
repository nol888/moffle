from collections import OrderedDict
import pytest

from acl import AccessControl

TEST_INTEGRATION_INPUTS = OrderedDict((
    (
        "default deny",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
            ),
            'test@example.com', 'net', '#channel',
            False,
        ),
    ),
    (
        "allow user named network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
            ),
            'test@example.com','net', None,
            True,
        ),
    ),
    (
        "allow user multiple named network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net2'), ('root', 'root')),
            ),
            'test@example.com','net', None,
            True,
        ),
    ),
    (
        "allow user named network and channel",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('network', 'net')),
            ),
            'test@example.com','net', '#channel',
            True,
        ),
    ),
    (
        "allow user named network does not grant channel",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
            ),
            'test@example.com', 'net', '#channel',
            False,
        ),
    ),
    (
        "allow user named channel does not grant network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('root', 'root')),
            ),
            'test@example.com', 'net', None,
            False,
        ),
    ),
    (
        "deny user named network to other user",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
            ),
            'test2@example.com', 'net', None,
            False,
        ),
    ),
    (
        "deny user named network to other network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
            ),
            'test@example.com', 'othernet', None,
            False,
        ),
    ),
    (
        "deny user channel on named network to other network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('network', 'net')),
            ),
            'test@example.com', 'othernet', '#channel',
            False,
        ),
    ),
    (
        "allow wildcard network fixed user",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', '*'), ('root', 'root')),
            ),
            'test@example.com', 'net', None,
            True,
        ),
    ),
    (
        "deny wildcard network wildcard user",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', '*'), ('root', 'root')),
            ),
            'test@example.com', 'net', None,
            False,
        ),
    ),
    (
        "allow wildcard wildcard scope fixed user access network",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('*', '*'), ('root', 'root')),
            ),
            'test@example.com', 'net', None,
            True,
        ),
    ),
    (
        "allow wildcard wildcard scope fixed user access channel",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('*', '*'), ('root', 'root')),
            ),
            'test@example.com', 'net', '#channel',
            True,
        ),
    ),
    (
        "allow user narrowing in child scope",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('network', 'net')),
            ),
            'test@example.com', 'net', '#channel',
            True,
        ),
    ),
    (
        "deny non-channel prefix",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '*'), ('network', 'net')),
            ),
            'test@example.com', 'net', 'notachannel',
            False,
        ),
    ),
    (
        "allow private message special token",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', 'PRIVATE_MESSAGE'), ('network', 'net')),
            ),
            'test@example.com', 'net', 'notachannel',
            True,
        ),
    ),
    (
        "allow private message on wildcard scope",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', 'test@example.com', ('*', 'PRIVATE_MESSAGE'), ('root', 'root')),
            ),
            'test@example.com', 'net', 'notachannel',
            True,
        ),
    ),
    (
        "allow acl groups",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', 'net'), ('root', 'root')),
                ('allow', ['test@example.com', 'test2@example.com'], ('channel', '#channel'), ('network', 'net')),
            ),
            'test@example.com', 'net', '#channel',
            True,
        ),
    ),
    (
        "allow channel groups",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', 'net'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', ['#channel', '#channel2']), ('network', 'net')),
            ),
            'test@example.com', 'net', '#channel2',
            True,
        ),
    ),
    (
        "allow network groups",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', ['net', 'net2']), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('network', 'net')),
            ),
            'test@example.com', 'net2', '#channel',
            True,
        ),
    ),
    (
        "allow parent and child value groups",
        (
            (
                ('deny', '*', ('*', '*'), ('root', 'root')),
                ('allow', '*', ('network', ['net', 'net2']), ('root', 'root')),
                ('allow', '*', ('network', 'net3'), ('root', 'root')),
                ('allow', 'test@example.com', ('channel', '#channel'), ('network', ['net2', 'net3'])),
            ),
            'test@example.com', 'net2', '#channel',
            True,
        ),
    ),
))

@pytest.mark.parametrize(
    "rules, email, network, channel, expected",
    TEST_INTEGRATION_INPUTS.values(),
    ids=list(TEST_INTEGRATION_INPUTS.keys()),
)
def test_integration(rules, email, network, channel, expected):
    ac = AccessControl(rules)
    assert ac._evaluate(email, network, channel) == expected
