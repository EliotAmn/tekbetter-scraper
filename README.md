# TekBetter - Data scraper

This is the data scraper which scrapes the data from the Epitech intranet and MyEpitech to sent it to the TekBetter API.

## How it works

You provide your microsoft auth cookies, and the scraper will use them to authenticate and scrape the data from the
intranet and MyEpitech.

There are two available modes:

- `Private mode`: You provide your own cookies in a configuration file, and the scraper will only scrape your data. It's
  recommended to secure your cookies by using a personal scraper.
- `Public mode`: The TekBetter server has a list of cookies, and accounts will be shared between all scrapers. This is
  only used for user who can't use a personal scraper.

After scraping the data, the scraper will send it to the TekBetter API.

## Used data

The scraper will scrape the following data:

* From the `intra.epitech.eu`:
    * Your first/last name
    * Your Epitech campus name
    * All available projects, modules and activities
    * Your calendar
    * Other users photos
    * Your grades and GPA
    * Your credits
* From the `my.epitech.eu` (api.epitest.eu):
    * All your projects tests results ("Moulinettes")

## Configuration Examples

### `config.json` Sample

Below is a sample configuration file (`config.json`) required for the scraper:

```json
{
  "intervals": {
    "moulinettes": 5,
    "projects": 60,
    "planning": 120,
    "modules": 120,
    "profile": 120,
    "netsoul": 120
  },
  "students": [
    {
      "microsoft_session": "YOUR_MICROSOFT_SESSION_TOKEN_HERE",
      "tekbetter_token": "YOUR_TEKBETTER_TOKEN_HERE"
    }
  ]
}
```

### Run the Scraper with Docker CLI

To run the scraper using Docker CLI, use the following command:

```sh
docker run -d \
  --name tekbetter-scraper \
  --restart always \
  --env TEKBETTER_API_URL="https://tekbetter.ovh" \
  --env SCRAPER_MODE="private" \
  --env SCRAPER_CONFIG_FILE="/tekbetter/scrapers.json" \
  --volume /etc/localtime:/etc/localtime:ro \
  --volume $(pwd)/config.json:/tekbetter/scrapers.json \
  ghcr.io/eliotamn/tekbetter-scraper:latest
```

### Run the Scraper with Docker Compose

Alternatively, you can use a `docker-compose.yml` file to run the scraper. Before proceeding, ensure that your
`config.json` is in the same directory as the `docker-compose.yml` file:

```yml
services:
  tekbetter:
    container_name: tekbetter-scraper
    restart: always
    image: ghcr.io/eliotamn/tekbetter-scraper:latest
    environment:
      TEKBETTER_API_URL: "https://tekbetter.ovh"
      SCRAPER_MODE: "private"
      SCRAPER_CONFIG_FILE: "/tekbetter/scrapers.json"
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./config.json:/tekbetter/scrapers.json

  # Optional: Watchtower to automatically update the scraper if a new version is available
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 120
```

## Environment variables

The following environment variables are required:

- `TEKBETTER_API_URL`: The URL of the TekBetter API
- `PUBLIC_SCRAPER_TOKEN`: The token to authenticate to the TekBetter API, only for the `Public mode`
- `SCRAPER_MODE`: The mode of the scraper, either `private` or `public`
- `SCRAPER_CONFIG_FILE`: The path to the configuration file, only for the `Private mode`
- `MAX_THREADS`: The maximum number of threads to scrape users. Optional, default to `4`

