# signatures
Validates user signatures, checking for technical and policy issues


## Translating
```
$ cd src/
$ pybabel extract -F babel.cfg -k N_ -o messages.pot .
$ pybabel update -d translations/ -i messages.pot
```

Update the translations in src/translations/\<lang\>/LC\_MESSAGES/messages.po

```
$ pybabel compile -d translations
```
