* [About Redfish Crawler](#redfish-crawler)
  * [Requirements](#requirements)
  * [Setup](#setup)
     * [Crawler Standalone Script](#crawler-standalone-script)
     * [Crawler Standalone within a virtualenv](#crawler-standalone-within-a-virtualenv)
  * [Usage](#usage)

# Redfish Crawler
The Redfish Crawler is a python standalone cli tool for generating a folder structure with all of it's json responses for all available endpoint on a server's own [Redfish](https://www.dmtf.org/standards/redfish) implementation.

## Requirements
* iDRAC7,8 or newer
* Firmware version ```2.60.60.60``` or higher
* iDRAC administrative account
* Python >= ```3.6```
* [requirements.txt](requirements.txt)

## Setup
### Crawler Standalone Script
```bash
> git clone https://github.com/grafuls/redfish-crawler && cd redfish-crawler
> pip install -r requirements.txt
```
NOTE:
* This will allow the crawler script execution via ```./crawler.py```

### Crawler Standalone within a virtualenv
```bash
> git clone https://github.com/grafuls/redfish-crawler && cd redfish-crawler
> virtualenv .crawler_venv
> source .crawler_venv/bin/activate
> pip install -r requirements.txt
```
NOTE:
* Both setup methods above can be used within a virtualenv
* After using crawler, the virtual environment can be deactivated running the ```deactivate``` command

## Usage
```bash
> ./crawler.py -u root -p {PASS} -H mgmt-server-r640.example.com
```

NOTE:
* This will create a root directory with the server's shortname on the current working directory, which will include all endpoints directories and json output files.
* Some endpoints are blacklisted as data from those is deemed irrelevant and costly:
  - "jsonschemas"
  - "logservices"
  - "secureboot"
  - "lclog"
  - "assembly"
  - "metrics"
  - "memorymetrics"
  - "telemetryservice"
  - "sessions"
