# -*- coding: utf-8 -*-
from collections import namedtuple
from operator import itemgetter
import os
import re

from natsort import natsorted
import cachetools

from acl import AccessControl
import config
import exceptions
import looseboy
import util

LOG_INTERMEDIATE_BASE = "moddata/log"
LOG_FILENAME_REGEX = re.compile("(?P<filename>(?P<network>(default|znc)+)_(?P<channel>[#&]*[a-zA-Z0-9/_\-\.\?\$]+)_(?P<date>\d{8})\.log)")

LogResult = namedtuple('LogResult', ['log', 'before', 'after'])

ldp = looseboy.LooseDateParser()

class LogPath:

    def __init__(self):
        self.ac = AccessControl(config.ACL)

    def networks(self):
        base_contents = os.listdir(config.LOG_BASE)

        dirs = [
            network for network in base_contents
            if os.path.isdir(
                self.network_to_path(network)
            ) and self.ac.evaluate(util.Scope.NETWORK, network)
        ]

        return sorted(dirs)

    def channels(self, network):
        matches = self._channels_list(network)

        # This network doesn't actually exist.
        if matches is None:
            raise exceptions.NoResultsException()

        # User is not allowed to view this network.
        if not self.ac.evaluate(util.Scope.NETWORK, network):
            raise exceptions.NoResultsException()

        channels = natsorted({
            filename['channel']
            for filename in matches
            if self.ac.evaluate(util.Scope.CHANNEL, filename['channel'])
        })

        return channels

    def channel_dates(self, network, channel):
        matches = self._channels_list(network)

        if matches is None:
            raise exceptions.NoResultsException()

        if not self.ac.evaluate(util.Scope.CHANNEL, channel):
            raise exceptions.NoResultsException()

        dates = [filename['date'] for filename in matches if filename['channel'] == channel]

        return sorted(dates, reverse=True)


    def log(self, network, channel, date):
        matches = self._channels_list(network)

        if matches is None:
            raise exceptions.NoResultsException()

        if not self.ac.evaluate(util.Scope.CHANNEL, channel):
            raise exceptions.NoResultsException()

        try:
            self._maybe_channel(network, channel, matches)
        except (
            exceptions.NoResultsException,
            exceptions.MultipleResultsException,
            exceptions.CanonicalNameException,
        ):
            raise

        parsed_date = ldp.parse(date)
        if parsed_date != date:
            raise exceptions.CanonicalNameException(util.Scope.DATE, parsed_date)

        channel_files = [filename for filename in matches if filename['channel'] == channel]
        channel_files = sorted(channel_files, key=itemgetter('date'))

        log = [filename for filename in channel_files if filename['date'] == date]

        if len(log) == 0:
            raise exceptions.NoResultsException()

        log = log[0]
        log_idx = channel_files.index(log)

        before, after = None, None
        if log_idx > 0:
            before = channel_files[log_idx - 1]['date']
        if log_idx < len(channel_files) - 1:
            after = channel_files[log_idx + 1]['date']

        log_path = os.path.join(self.network_to_path(network), log['filename'])

        # Enumerate at 1: these are log line numbers.
        log_file = enumerate(open(log_path, errors='ignore').readlines(), start=1)

        return LogResult(log_file, before, after)

    @cachetools.lru_cache(maxsize=128)
    def network_to_path(self, network):
        return os.path.join(config.LOG_BASE, network, LOG_INTERMEDIATE_BASE)

    def _maybe_channel(self, network, channel, matches):
        # This looks a bit intensive.
        # Accomodate partial matches to see if containing-match only matches
        # one channel. If it does, we can 302 to the real URL, but otherwise
        # we should 404.
        maybe_channels = {filename['channel'] for filename in matches if channel in filename['channel']}

        # Bail if it's ambiguous...
        if len(maybe_channels) > 1:
            # unless one of them is an exact match.
            exact = [maybe_channel for maybe_channel in maybe_channels if maybe_channel == channel]
            if len(exact) != 1:
                raise exceptions.MultipleResultsException()
        elif len(maybe_channels) == 1:
            canonical_channel = list(maybe_channels)[0]

            if channel != canonical_channel:
                raise exceptions.CanonicalNameException(util.Scope.CHANNEL, canonical_channel)
        elif len(maybe_channels) == 0:
            # We have nothing. It is unfortunate.
            raise exceptions.NoResultsException()

    @cachetools.ttl_cache(maxsize=128, ttl=21600)
    def _channels_list(self, network):
        channel_base = self.network_to_path(network)

        if not os.path.exists(channel_base):
            return None

        files = os.listdir(channel_base)

        file_matches = [LOG_FILENAME_REGEX.match(filename) for filename in files]
        file_matches = [match.groupdict() for match in file_matches if match is not None]

        return file_matches