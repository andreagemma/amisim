## Unreleased

- Added a structured CLI entrypoint with `run`, `server`, and `init_db` commands.
- Added `run` defaults for `settings.ini` and `parmas.json` auto-discovery in current working directory when explicit paths are omitted.
- Added support for repeatable `-e/--env KEY=VALUE` runtime environment overrides in `run` mode.
- Added textual help aliases: `amisim help` for global help and `amisim <command> help` for subcommand help.
- Added library-facing `AmisimApplication` class exposing prepared stubs for `init_db`, `load_settings`, `load_params`, and `run`.
- Added unit tests for CLI parsing and helper behavior.
- Added dedicated documentation pages for CLI and library usage in `docs/cli.md` and `docs/library.md`.
- Added runtime dependency on `ga-configreader`.
- Added runtime dependency on `SQLAlchemy`.
- Added runtime dependency on `loguru`.
- Added runtime dependency on `ga-tictoc`.
- Added third-party licensing records for `ga-configreader` in `licenses/third_party/summary.tsv`, package license archive, and notice files.
- Added third-party licensing records for `SQLAlchemy` in `licenses/third_party/summary.tsv`, package license archive, and notice files.
- Added third-party licensing records for `loguru` in `licenses/third_party/summary.tsv`, package license archive, and notice files.
- Added third-party licensing records for `ga-tictoc` in `licenses/third_party/summary.tsv`, package license archive, and notice files.
- Clarified documentation and CLI help semantics: `settings` contains base software configuration and `params` contains algorithm execution parameters.
- Refactored the internal DB module with stronger typing and safer initialization/session handling while preserving public API names.
- Wired `AmisimApplication.init_db` to initialize the internal DB and configure loguru logging with DB persistence sink.
- Added optional schema support for internal DB tables via `init_db`/`open_db` and `amisim init_db --schema` CLI option.
- Added `amisim run -O/--option SECTION:NAME=VALUE` repeatable settings overrides, parsed into nested dictionaries through reusable utils helpers.
- Implemented `load_settings` using `ga-configreader`, including dynamic `DATABASE_SETTINGS` DB-backed reconfiguration when enabled.
- Added LOGGING-driven `loguru` configuration with colorized format conversion, `execution_id` context, and elapsed/last_elapsed runtime fields.
- Added `AmisimLogger` inheriting from `ga-tictoc` `TicToc`, bridged to `loguru` sinks for console/file/DB output.

Model4Italy Proprietary Software License

Copyright (c) 2026 Andrea Gemma. All rights reserved.

This software and related documentation (the "Software") are proprietary.
No part of the Software may be used, copied, modified, distributed,
sublicensed, sold, rented, leased, reverse-engineered, decompiled,
or otherwise exploited except as expressly authorized by a valid written
license agreement with the copyright holder.

Unauthorized use is strictly prohibited.

Third-party components
This Software may include or depend on third-party open source components.
Those components remain licensed under their respective licenses.
Applicable notices and license texts are provided in:
- THIRD_PARTY_NOTICES.md
- licenses/third_party/packages/

DISCLAIMER
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE SOFTWARE IS PROVIDED
"AS IS" AND "AS AVAILABLE", WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO MERCHANTABILITY, FITNESS FOR
A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT.

LIMITATION OF LIABILITY
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
CONSEQUENTIAL, OR EXEMPLARY DAMAGES ARISING OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR ITS USE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
