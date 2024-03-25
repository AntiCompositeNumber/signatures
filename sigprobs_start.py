#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import subprocess
import json
import sys

config = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {
        "name": "signatures.sigprobs",
        "namespace": "tool-signatures",
        "labels": {"name": "signatures.sigprobs", "toolforge": "tool"},
    },
    "spec": {
        "ttlSecondsAfterFinished": 86400,  # 1 day
        "backoffLimit": 2,
        "template": {
            "metadata": {
                "labels": {"name": "signatures.sigprobs", "toolforge": "tool"},
            },
            "spec": {
                "containers": [
                    {
                        "name": "sigprobs",
                        "image": (
                            "docker-registry.tools.wmflabs.org/"
                            "toolforge-python39-sssd-base:latest"
                        ),
                        "command": [
                            "/data/project/signatures/signatures/venv/bin/python3",
                            "/data/project/signatures/signatures/src/sigprobs.py",
                        ],
                        "args": sys.argv[1:],
                        "workingDir": "/data/project/signatures",
                        "env": [{"name": "HOME", "value": "/data/project/signatures"}],
                        "imagePullPolicy": "Always",
                    }
                ],
                "restartPolicy": "Never",
            },
        },
    },
}
p = subprocess.run(
    ["kubectl", "apply", "--validate=true", "-f", "-"],
    input=json.dumps(config),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
)
print(p.stdout)
sys.exit(p.returncode)
