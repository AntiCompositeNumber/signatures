#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import hmac
import logging
import subprocess
import json

import flask
import requests

bp = flask.Blueprint("deploy", __name__, url_prefix="/deploy")


def get_config(filename="/data/project/signatures/github_config.json"):
    try:
        with open(filename) as f:
            config = json.load(f)
    except Exception:
        config = {}
    return config


config = get_config()


def pull_master():
    logging.info("Pulling from git repository")
    try:
        pull = subprocess.run(
            [
                "git",
                "-C",
                "/data/project/signatures/signatures/",
                "pull",
            ],
            check=True,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as cpe:
        logging.debug(pull.stdout)
        logging.error(pull.stderr)
        logging.error(cpe)
        return False
    else:
        logging.debug(pull.stdout)
        logging.error(pull.stderr)
        return True


def restart_webservice():
    logging.info("Webservice restarting!")
    subprocess.Popen(["webservice", "restart"])


def update_status(url, status, auth):
    payload = {"state": status}
    headers = {"Accept": "application/vnd.github.flash-preview+json"}
    response = requests.post(url, auth=auth, json=payload, headers=headers)
    logging.debug(response.text)
    return response.status_code == 201


def deploy(request, payload):
    logging.info("Deployment starting")
    logging.debug(payload)
    auth = ("AntiCompositeNumber", config["github_deploy_pat"])
    status_url = payload["deployment"]["statuses_url"]
    if pull_master():
        update_status(status_url, "success", auth)
        restart_webservice()
        return True
    else:
        update_status(status_url, "error", auth)
        return False


def check_status(payload):
    return payload.get("deployment_status", {}).get("state") == "pending"


def verify_hmac(request):
    r_hmac = hmac.new(
        (config["github_secret"]).encode(), msg=request.get_data(), digestmod="sha1"
    )
    r_digest = "sha1=" + r_hmac.hexdigest()
    g_digest = request.headers["X-Hub-Signature"]
    return hmac.compare_digest(r_digest, g_digest)


@bp.route("/", methods=["POST"])
def autodeploy():
    request = flask.request
    logging.debug("Request:" + str(request.__dict__))
    logging.debug("Request JSON:" + str(request.json))
    if check_status(request.json) and verify_hmac(request):
        try:
            deploy_result = deploy(request, request.json)
        except Exception as problem:
            logging.error(problem)
            return "Exception while deploying:\n" + str(problem), 500
        if deploy_result:
            return "", 204
        else:
            flask.abort(504)
    else:
        flask.abort(403)
