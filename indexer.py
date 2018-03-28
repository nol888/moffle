try:
    import gevent
    import gevent.pool
    import gevent.monkey

    gevent.monkey.patch_all()
except ImportError:
    gevent = False

try:
    import re2 as re
except ImportError:
    import re

import argparse
from time import asctime

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from elasticsearch_dsl import Search

import config
import log_path
from util import log


LINE = re.compile(
    r'^\[(?P<time>\d{2}:\d{2}:\d{2})\] (?P<line_type>\* |<|\*\*\* (?:Join|Part|Quit)s: )(?P<author>[^ >]+)>?(?P<text>.+)'
)
TYPE_MAP = {
    '* ': 'action',
    '<': 'normal',
    '*** Joins: ': 'join',
    '*** Parts: ': 'part',
    '*** Quits: ': 'quit',
}


class IndexerAccessControl:
    def evaluate(*args):
        return True


def configure(es, delete_index):
    if delete_index:
        if es.indices.exists(index='moffle'):
            log("Deleting index")
            log(es.indices.delete(index='moffle'))

    if not es.indices.exists(index='moffle'):
        log("Creating index")

        es.indices.create(
            index='moffle',
            body={
                'mappings': {
                    'logline': {
                        '_all': {'enabled': False},
                        'properties': {
                            'date': {'type': 'date', 'format': 'basic_date'},
                            'time': {'type': 'keyword', 'index': 'no'},
                            'network': {'type': 'keyword'},
                            'channel': {'type': 'keyword'},
                            'line_no': {'type': 'integer'},
                            'line_type': {'type': 'keyword'},
                        },
                    },
                },
            },
        )


def line_to_index_action(network, channel, date, i, line):
    m = LINE.match(line)
    if not m:
        # What happened here?
        return None

    fields = m.groupdict()
    fields['text'] = fields['text'].strip()
    fields['line_type'] = TYPE_MAP[fields['line_type']]

    fields.update({
        '_index': 'moffle',
        '_type': 'logline',
        'network': network,
        'channel': channel,
        'date': date,
        'line_no': i,
    })
    return fields


def index_single(es, network, channel, date, lines):
    # Delete existing
    delete_existing = Search(
        using=es,
        index='moffle',
    ).query(
        "term", network=network,
    ).query(
        "term", channel=channel,
    ).query(
        "term", date=date,
    )

    es.delete_by_query(
        index='moffle',
        body=delete_existing.to_dict(),
    )

    actions = [x for x in (line_to_index_action(network, channel, date, i, line) for i, line in lines) if x]
    while actions:
        retries = 0
        try:
            success_count, _ = bulk(es, actions)
            log("{}/{}/{}: indexed {} lines".format(network, channel, date, success_count))
            return success_count
        except Exception as e:
            retries += 1
            log("{}/{}/{}: Attempt {}/3: {}".format(network, channel, date, retries, e))
            if retries > 3:
                raise


def index_delta(es, network, channel, paths):
    channel_tip = Search(
        using=es,
        index='moffle',
    ).filter(
        "term", network=network,
    ).filter(
        "term", channel=channel,
    )[0:0]
    channel_tip.aggs.metric('max_date', 'max', field='date')
    max_date = channel_tip.execute().aggregations.max_date

    if max_date.value:
        max_date = max_date.value_as_string
    else:
        max_date = ''

    max_line_no = 0
    if max_date:
        date_tip = Search(
            using=es,
            index='moffle',
        ).filter(
            "term", network=network,
        ).filter(
            "term", channel=channel,
        ).filter(
            "term", date=max_date,
        )[0:0]
        date_tip.aggs.metric('max_line_no', 'max', field='line_no')
        max_line_no = int(date_tip.execute().aggregations.max_line_no.value)

    log('{}/{} == {}:{}'.format(network, channel, max_date, max_line_no))

    for date in paths.channel_dates(network, channel)[::-1]:
        if date < max_date:
            continue

        logfile_path = paths.date_to_path(network, channel, date)
        logfile = list(enumerate(open(logfile_path, errors='ignore').readlines(), start=1))

        if date > max_date:
            index_single(es, network, channel, date, logfile)
            continue

        actions = (
            line_to_index_action(network, channel, date, i, line)
            for i, line in logfile
            if i > max_line_no
        )
        actions = [x for x in actions if x]

        while actions:
            retries = 0
            try:
                success_count, _ = bulk(es, actions)

                if success_count != len(actions):
                    log("{}/{} !! {}: {}/{} actions successful".format(network, channel, date, success_count, len(actions)))
                    break

                log("{}/{} -> {}:{} ({} actions successful)".format(network, channel, date, len(logfile), success_count))
                break
            except Exception as e:
                retries += 1
                log("{}/{} !! {} Attempt {}/3: {}".format(network, channel, date, retries, e))
                if retries > 3:
                    raise


def main(dofn):
    # TODO: use these parameters
    parser = argparse.ArgumentParser()
    parser.add_argument('--delta', action='store_true', help='use delta indexing scheme (ignores date arguments)')
    parser.add_argument('--delete-index', action='store_true', help='delete index before indexing')
    parser.add_argument('--start-date', help='index logs with dates after the given date')
    parser.add_argument('--end-date', help='index logs with dates before the given date')
    args = parser.parse_args()

    es = Elasticsearch(config.ES_HOST, timeout=30)
    configure(es, delete_index=args.delete_index)

    paths = getattr(log_path, config.LOG_PATH_CLASS)(IndexerAccessControl())

    for network in paths.networks():
        for channel in paths.channels(network):
            if args.delta:
                # dofn(index_delta, es, network, channel, paths)
                index_delta(es, network, channel, paths)
            else:
                for date in paths.channel_dates(network, channel):
                    logfile_path = paths.date_to_path(network, channel, date)
                    logfile = enumerate(open(logfile_path, errors='ignore').readlines(), start=1)
                    dofn(index_single, es, network, channel, date, logfile)


if __name__ == "__main__":
    if gevent:
        index_pool = gevent.pool.Pool(size=20)
        main(lambda *args, **kwargs: index_pool.spawn(*args, **kwargs))
        index_pool.join()
    else:
        main(lambda fn, *args, **kwargs: fn(*args, **kwargs))

