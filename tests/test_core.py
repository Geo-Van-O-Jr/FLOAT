from dataclasses import replace
import pytest

from float_app.commands import Command, CommandParser
from float_app.config import GestureSettings, Settings
from float_app.gestures import GestureEngine, HandSample
from float_app.speech_logic import Segmenter, choose_command
from float_app.state import Session

POINT = HandSample(.5, .5, 1, 1, True, False)
PINCH = replace(POINT, index_pinch=.2, index_up=False)
RIGHT = replace(POINT, middle_pinch=.2, middle_up=False)
SCROLL = replace(POINT, middle_up=True)


def prepared():
    engine = GestureEngine(GestureSettings(), 1280, 720)
    engine.update(POINT, 0)
    return engine


def test_short_pinch_clicks_once_on_release():
    e = prepared()
    assert e.update(PINCH, .1) == []
    assert e.update(PINCH, .2) == []
    result = e.update(POINT, .25)
    assert [(x.kind, x.value) for x in result] == [("click", "left")]
    assert all(a.kind != "click" for a in e.update(POINT, .3))


def test_two_short_pinches_emit_two_clicks():
    e = prepared()
    result = []
    for hand, timestamp in [(PINCH, .05), (POINT, .1), (PINCH, .16), (POINT, .21)]:
        result += e.update(hand, timestamp)
    assert [x.kind for x in result] == ["click", "click"]


def test_hold_drags_once_and_releases_without_extra_click():
    e = prepared()
    e.update(PINCH, .1)
    assert [x.kind for x in e.update(PINCH, .46)] == ["down"]
    assert [x.kind for x in e.update(replace(PINCH, x=.65), .5)] == ["move"]
    assert [x.kind for x in e.update(POINT, .6)] == ["up"]


def test_hysteresis_avoids_pinch_chatter():
    e = prepared()
    e.update(PINCH, .1)
    for time, distance in [(.12, .4), (.14, .5), (.16, .3), (.18, .54)]:
        assert e.update(replace(PINCH, index_pinch=distance), time) == []
    assert e.update(replace(POINT, index_pinch=.56), .2)[0].kind == "click"


def test_loss_during_drag_releases_exactly_once():
    e = prepared()
    e.update(PINCH, .1)
    e.update(PINCH, .5)
    assert e.update(None, .6) == []
    assert [a.kind for a in e.update(None, .8)] == ["up"]
    assert e.update(None, .9) == []


def test_loss_during_short_pinch_never_clicks():
    e = prepared()
    e.update(PINCH, .1)
    assert e.update(None, .4) == []
    assert all(a.kind != "click" for a in e.update(POINT, .5))


def test_new_hand_pinching_does_not_click_before_pointing():
    e = GestureEngine(GestureSettings(), 1280, 720)
    assert e.update(PINCH, 0) == []
    assert all(a.kind != "click" for a in e.update(POINT, .1))


def test_right_click_and_scroll_transition():
    e = prepared()
    e.update(RIGHT, .1)
    assert e.update(POINT, .2)[0].value == "right"
    assert e.update(SCROLL, .3) == []
    result = e.update(replace(SCROLL, y=.35), .4)
    assert result[0].kind == "scroll" and result[0].value > 0
    assert e.update(POINT, .5)[0].kind == "move"
    assert e.update(SCROLL, .6) == []


def test_pause_reset_releases_drag_and_forgets_pointer():
    e = prepared()
    e.update(PINCH, .1)
    e.update(PINCH, .5)
    assert e.reset()[0].kind == "up"
    assert e.pointer is None and e.mode == "idle"


def test_pointer_clamped_and_smoothed():
    e = prepared()
    point = e.update(replace(POINT, x=2, y=-1), .033)[0].value
    assert 640 < point[0] < 1279 and 0 < point[1] < 360
    for i in range(1, 50):
        point = e.update(replace(POINT, x=2, y=-1), .033 * (i + 1))[0].value
    assert point == (1279, 0)


@pytest.mark.parametrize("text", ["ativar", "o computador ativar", "computador ativar e apagar tudo", "computador", "vamos abrir navegador"])
def test_commands_require_full_exact_addressed_phrase(text):
    assert CommandParser().parse(text) is None


def test_commands_accept_accents_punctuation_and_case():
    assert CommandParser().parse("Computador, ABRIR CONFIGURAÇÕES!") == Command("settings")


def test_aliases_are_registered_paths_not_shell_commands():
    parser = CommandParser({"meu editor": r"D:\Apps\editor.exe"})
    assert parser.parse("computador abrir meu editor") == Command("custom_app", r"D:\Apps\editor.exe")
    assert parser.parse("computador abrir powershell") is None
    with pytest.raises(ValueError):
        CommandParser({"calculadora": "some.exe"})
    with pytest.raises(ValueError):
        CommandParser({"aplicação": "a.exe", "aplicacao": "b.exe"})


def test_constrained_decoder_cannot_invent_wake_word():
    command, addressed = choose_command(CommandParser(), "vamos conversar", .95, "computador clicar", 1)
    assert command is None and not addressed


def test_uncertain_command_is_not_executed():
    command, addressed = choose_command(CommandParser(), "computador clicar", .1, "computador clicar", .4)
    assert command is None and addressed


def test_state_invalidates_old_audio_and_inference():
    s = Session()
    old = s.transition("dictation", 10)
    assert s.accepts(old)
    s.transition("paused")
    assert not s.accepts(old)


def test_window_change_suspends_even_if_user_switches_back():
    s = Session()
    old = s.transition("dictation", 10)
    assert s.focus_changed(11)
    assert not s.accepts(old)
    assert not s.focus_changed(10)
    assert s.snapshot().mode == "dictation_suspended"
    resumed = s.transition("dictation", 10)
    assert s.accepts(resumed) and not s.accepts(old)


def test_segmenter_drops_silence_and_short_noise():
    segmenter = Segmenter()
    assert all(segmenter.feed(bytes(640), False) is None for _ in range(100))
    for _ in range(3):
        segmenter.feed(bytes(640), True)
    assert all(segmenter.feed(bytes(640), False) is None for _ in range(40))


def test_segmenter_preserves_one_phrase_and_has_bounded_length():
    segmenter = Segmenter()
    results = []
    for speech in [True] * 50 + [False] * 40:
        result = segmenter.feed(bytes(640), speech)
        if result:
            results.append(result)
    assert len(results) == 1
    for _ in range(600):
        result = segmenter.feed(bytes(640), True)
        if result:
            assert len(result) <= 600 * 640
            return
    pytest.fail("Continuous speech did not split at the buffer bound")


def test_settings_round_trip_and_invalid_roi(tmp_path):
    settings = Settings(configured=True)
    settings.gesture.hand = "Left"
    settings.gesture.roi = [.2, .2, .7, .8]
    file = tmp_path / "settings.json"
    settings.save(file)
    assert Settings.load(file) == settings
    settings.gesture.roi = [.5, .5, .55, .55]
    with pytest.raises(ValueError):
        settings.save(file)

