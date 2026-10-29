"""Executed inside Search before any test HTTP request. Never contact a vendor."""
import json
import socket
import sys


def check_dns(resolve, expected):
    for host in ('api.firecrawl.dev', 'api.brightdata.com', 'paid-sink'):
        addresses = {row[4][0] for row in resolve(host, 443, type=socket.SOCK_STREAM)}
        assert addresses == set(expected), f'{host}: {addresses} != sink {expected}'
        print(host, 'resolves ONLY to sink:', sorted(addresses), flush=True)


def check_no_route(connect):
    # A DNS alias is not a firewall. Prove literal-IP TCP egress is blocked as well.
    for address in ('1.1.1.1', '2606:4700:4700::1111'):
        try:
            conn = connect((address, 443), timeout=1)
        except OSError:
            print('external TCP blocked:', address, flush=True)
        else:
            conn.close()
            raise AssertionError('Search has external TCP egress: ' + address)


if __name__ == '__main__':
    check_dns(socket.getaddrinfo, json.loads(sys.argv[1]))
    check_no_route(socket.create_connection)
