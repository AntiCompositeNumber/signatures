# signatures
![GitHub Workflow Status](https://img.shields.io/github/workflow/status/AntiCompositeNumber/signatures/Python%20application)
![Uptime Robot status](https://img.shields.io/uptimerobot/status/m784569439-67298a1a3ff3bf5812aba175?label=website%20status)
[![Coverage Status](https://coveralls.io/repos/github/AntiCompositeNumber/signatures/badge.svg?branch=master)](https://coveralls.io/github/AntiCompositeNumber/signatures?branch=master)
![GitHub Pipenv locked Python version](https://img.shields.io/github/pipenv/locked/python-version/AntiCompositeNumber/signatures)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Validates user signatures, checking for technical and policy issues

## Operation
This tool consists of two parts: a webservice and a backend batch report runner.

### Webservice
On Toolforge, the repo is symlinked to ~/www/python/

To start the webservice, run `webservice --backend=kubernetes python3.7 start`

To stop the webservice, run `webservice stop`

### Batch reports
On Toolforge, reports are run from a Kubernetes Job. 
A custom script is used to start the job. 
Any arguments passed to the start script will be passed to the report script. 

See `python3 src/sigprobs.py --help` for CLI details.

To create or update a report, run `./sigprobs_start.py <site>`

For example, a report for the English Wikipedia can be run with `./sigprobs_start.py en.wikipedia.org`

## Translating
```
$ cd src/
$ pybabel extract -F babel.cfg -k N_ -o messages.pot .  # Extract translatable strings
$ pybabel update -d translations/ -i messages.pot  # Update existing message catalogs
$ pybabel init -i messages.pot -d translations/ -l <lang>  # Create new message catalog
```

Update the translations in src/translations/\<lang\>/LC\_MESSAGES/messages.po

```
$ pybabel compile -d translations
```
