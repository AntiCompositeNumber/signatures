#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2020 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
                            "toolforge-python37-sssd-base:latest"
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
        }
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
