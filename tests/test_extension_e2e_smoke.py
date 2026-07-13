import inspect

import pytest

from scripts import extension_e2e_smoke as smoke


def test_report_accepts_passed_and_unsupported_browser_checks():
    smoke.validate_report(
        [
            smoke.CheckResult("loaded", "passed", "ok"),
            smoke.CheckResult("optional_api", "skipped", "unavailable"),
        ]
    )


def test_report_names_every_failed_contract():
    with pytest.raises(smoke.ExtensionSmokeError) as failure:
        smoke.validate_report(
            [
                smoke.CheckResult("service_worker_restart", "failed", "timeout"),
                smoke.CheckResult("offline_queue", "failed", "not persisted"),
            ]
        )
    assert "service_worker_restart: timeout" in str(failure.value)
    assert "offline_queue: not persisted" in str(failure.value)


def test_loaded_extension_smoke_is_persistent_headless_and_behavioral():
    source = inspect.getsource(smoke.run_smoke)
    assert "launch_persistent_context" in source
    assert 'channel="chromium"' in source
    assert "headless=True" in source
    assert "--disable-extensions-except" in source
    assert "--load-extension" in source
    restart_source = inspect.getsource(smoke._restart_extension)
    assert '"Target.closeTarget"' in restart_source
    assert '"service_worker"' in restart_source
    for contract in (
        "permissions",
        "context_menu_registration",
        "side_panel",
        "live_api_pairing",
        "service_worker_restart",
        "context_menu_save",
        "sanitized_capture",
        "offline_queue",
        "reading_list",
    ):
        assert contract in source


def test_smoke_defaults_to_disposable_profile_and_data_directories():
    source = inspect.getsource(smoke.main)
    assert "bop-extension-profile-" in source
    assert "bop-extension-data-" in source
    assert "profile_temp.cleanup()" in source
    assert "data_temp.cleanup()" in source
