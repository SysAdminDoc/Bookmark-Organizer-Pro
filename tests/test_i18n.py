from bookmark_organizer_pro import i18n


def test_gettext_template_is_current():
    assert i18n.POT_PATH.read_text(encoding="utf-8") == i18n.build_pot()


def test_i18n_check_cli_passes_when_template_is_current(capsys):
    result = i18n.main(["--check"])

    captured = capsys.readouterr()
    assert result == 0
    assert "is current" in captured.out
