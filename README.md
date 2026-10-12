# leadgrab

Turn a city + business type into a clean, verified lead list.

```
$ python3 leadgrab.py --cities Austin "San Diego" --categories dentists gyms --out leads.csv
  'dentists in Austin': 21 businesses
  'gyms in Austin': 22 businesses
  ...
287 leads in 2282s -> leads.csv
  with phone: 186 | with website: 269
```

## What you get

One CSV row per business:

| column | example |
|---|---|
| name | Powerhouse Gym |
| category | gyms |
| type | Fitness center |
| address | 158 W. 27th Street, New York, NY |
| city | New York |
| rating | 4.8 |
| reviews | 435 |
| phone | (646) 429-9278 |
| website | https://www.powerhousegymnyc.com |
| cid | 2191807775245230468 |

## Setup

Needs a scraping gateway token (Bright Data Web Unlocker works; any gateway
that accepts `{"url", "zone", "format"}` JSON works via `LEADGRAB_GATEWAY`).

```bash
export BRIGHTDATA_TOKEN=your_token
export BRIGHTDATA_ZONE=unlocker1
```

Requires Python 3.8+, standard library only. No pip installs.

## Usage

```bash
# one-off query
python3 leadgrab.py "coffee shops in Miami" --out miami_coffee.csv

# sweep: cities x categories
python3 leadgrab.py --cities Chicago Denver \
                     --categories plumbers "hvac contractors" \
                     --out midwest.csv

# fast mode: skip the phone/website second pass (~15x faster, less complete)
python3 leadgrab.py "restaurants in Seattle" --no-enrich
```

## Sample data

[`sample/leads_sample_50.csv`](sample/leads_sample_50.csv) — 45 real records
from a live run (gyms, dentists, restaurants, plumbers across 5 US cities),
phone + website included where the listing publishes them.

## Notes

- Rate: ~4s per request through the gateway, 4 workers by default
  (`--workers 8` if your plan allows). Enrichment adds ~8s per row.
- Google sometimes returns an empty local block for a query; re-run it,
  it's transient.
- Only pulls published business contact details (public listings), not
  personal data.

## License

MIT
