import urllib.request, urllib.parse

q = open('/work/overpass_volda.txt').read()
data = urllib.parse.urlencode({'data': q}).encode()
print('querying overpass for Volda buildings...')
req = urllib.request.Request(
    'https://overpass-api.de/api/interpreter',
    data=data,
    headers={
        'User-Agent': 'Streif-spike/0.1 (contact@semden.info)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*',
    },
)
resp = urllib.request.urlopen(req, timeout=300)
b = resp.read()
open('/work/volda.osm', 'wb').write(b)
print('volda.osm bytes:', len(b))
