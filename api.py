from itertools import chain
import functools
import hmac
from base64 import urlsafe_b64decode
from hashlib import sha256

import flask_restful
from flask import Blueprint
from flask import g
from flask import request
from flask import url_for
from flask_restful import Resource
from flask_restful import reqparse

import config
from exceptions import ApiNotAuthorizedException

errors = {
    'ApiNotAuthorizedException': {
        'message': "You are not authorized to access this resource.",
        'status': 403
    }
}
api = Blueprint('api', __name__)
rest_api = flask_restful.Api(api, catch_all_404s=True, errors=errors)

def authenticated(fn):
    def generate_hmac(key, path, args):
        """
        Hash the request path plus all query params in lexicographic order.
        """
        path = path.encode('utf_8') + b'?'
        args = '&'.join(sorted(["{}={}".format(k, v) for k, v in args.items()])).encode('utf_8')

        m = hmac.new(key, digestmod=sha256)
        m.update(path)
        m.update(args)
        return m.digest()

    @functools.wraps(fn)
    def wrap(*args, **kwargs):
        if 'uid' not in request.args or 'sig' not in request.args:
            raise ApiNotAuthorizedException()

        uid = request.args['uid']
        sig = urlsafe_b64decode(request.args['sig'])
        if uid not in config.API_KEYS:
            raise ApiNotAuthorizedException()

        hmac_key = config.API_KEYS[uid]
        request_args = {k: v for k, v in request.args.items() if not k == 'sig'}
        expected_sig = generate_hmac(hmac_key, request.path, request_args)
        if not hmac.compare_digest(sig, expected_sig):
            raise ApiNotAuthorizedException()

        g.uid = uid

        return fn(*args, **kwargs)

    return wrap


class Search(Resource):
    @authenticated
    def get(self, network, channel):
        from app import grep

        parser = reqparse.RequestParser()
        parser.add_argument('q', type=str, required=True)
        args = parser.parse_args()

        hits_grouped = grep.run(
            channels=[channel],
            network=network,
            query=args['q']
        )
        results = [{
            'date': hit.date,
            'lines': [{
                'line_marker': line.line_marker,
                'line_no': line.line_no,
                'line': line.line
            } for line in hit.lines]
        } for hit in chain.from_iterable(hits_grouped)] if hits_grouped else []

        return {
            'total_results': len(results),
            'canonical_url': url_for('search', network=network, channel=channel, query=args['q']),
            'results': results
        }


rest_api.add_resource(Search, '/search/<string:network>/<string:channel>')
