# Copyright 2026 Dynamo Foundry LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Synology Share Downloader -- reliable, resumable downloads from Synology
folder-share links (the gofile.me / QuickConnect kind), file by file."""

__version__ = "1.0.0"

APP_NAME = "Synology Share Downloader"
COMPANY = "Dynamo Foundry LLC"
COMPANY_TAGLINE = "a Software Company"
COPYRIGHT = "Copyright © 2026 Dynamo Foundry LLC"
LICENSE_NAME = "Apache License 2.0"
LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0"
REPO_URL = "https://github.com/shawnrancatore/synology-share-downloader"
DOCS_URL = REPO_URL + "/blob/main/docs/USAGE.md"

__all__ = [
    "__version__", "APP_NAME", "COMPANY", "COMPANY_TAGLINE", "COPYRIGHT",
    "LICENSE_NAME", "LICENSE_URL", "REPO_URL", "DOCS_URL",
]
